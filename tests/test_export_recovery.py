"""Interruption and request-boundary regressions, without Google or Android."""
import json

import pytest

from core import docs_helper as docs
from test_smoke import (FakeGoogleDocState, FakeDocsService, FakeDocumentsResource,
                        FakeDriveService, FakeDriveState, FakeFilesResource, _http_error,
                        _crea_esercizio_di_prova)


def test_checkpoint_precedes_remote_mutation_and_survives_process_exit(tmp_path, monkeypatch):
    state = tmp_path / 'state.json'
    snapshots = []
    remote = FakeGoogleDocState()
    original = FakeDocumentsResource.batchUpdate

    def interrupt(self, documentId, body):
        persisted = json.loads(state.read_text())
        assert persisted['doc_id'] == remote.doc_id
        assert persisted['pending']
        assert snapshots[-1] == persisted
        original(self, documentId, body)
        raise SystemExit('process killed after server applied mutation')

    monkeypatch.setattr(FakeDocumentsResource, 'batchUpdate', interrupt)
    with pytest.raises(SystemExit):
        docs.create_workout_document(
            [], 'Sheet', docs_service=FakeDocsService(remote),
            drive_service=FakeDriveService(FakeDriveState()), state_path=str(state),
            checkpoint_callback=lambda: snapshots.append(json.loads(state.read_text())))
    assert remote.create_calls == 1
    assert json.loads(state.read_text())['pending']


def test_ambiguous_create_is_not_automatically_repeated(tmp_path, monkeypatch):
    state = tmp_path / 'state.json'
    calls = []

    def create(self, body):
        calls.append(body)
        raise _http_error(503)

    monkeypatch.setattr(FakeDocumentsResource, 'create', create)
    for _ in range(2):
        with pytest.raises(docs.GoogleDocsError):
            docs.create_workout_document([], 'Sheet',
                docs_service=FakeDocsService(FakeGoogleDocState()),
                drive_service=FakeDriveService(FakeDriveState()), state_path=str(state))
    assert len(calls) == 1


def test_checkpoint_bundle_survives_work_directory_reextraction(tmp_path):
    from core.scheda_file import salva_scheda, carica_scheda
    from kivy_app.editor import SchedaEditorController
    from kivy_app.export import DocExportController
    bundle = tmp_path / 'workout.scheda'
    salva_scheda([_crea_esercizio_di_prova('Squat', tmp_path)], bundle)
    exercises, work = carica_scheda(bundle)
    editor = SchedaEditorController.da_bundle(exercises, str(bundle), work)

    def creator(exercises, title, **kwargs):
        docs.salva_stato(kwargs['state_path'], {'doc_id': 'persisted', 'esercizi': [],
                                               'pending': {'phase': 'document_mutation'}})
        kwargs['checkpoint_callback']()
        raise SystemExit('no exception handler or final save')

    with pytest.raises(SystemExit):
        DocExportController(editor, creator=creator).genera()
    _, reopened = carica_scheda(bundle)
    from core.scheda_file import percorso_stato
    assert docs.carica_stato(percorso_stato(reopened))['doc_id'] == 'persisted'


@pytest.mark.parametrize('damage', ['none', 'trash', 'empty_cell'])
def test_reopen_checks_remote_content_not_just_state(tmp_path, monkeypatch, damage):
    exercises = [_crea_esercizio_di_prova('Squat', tmp_path)]
    remote = FakeGoogleDocState()
    services = dict(docs_service=FakeDocsService(remote),
                    drive_service=FakeDriveService(FakeDriveState()),
                    state_path=str(tmp_path / 'state.json'))
    docs.create_workout_document(exercises, 'Sheet', **services)
    if damage == 'trash':
        from test_smoke import _RisultatoEseguibile
        monkeypatch.setattr(FakeFilesResource, 'get',
                            lambda *args, **kwargs: _RisultatoEseguibile({'trashed': True}))
    if damage == 'empty_cell':
        table = next(e['table'] for e in remote.content if 'table' in e)
        table['tableRows'][0]['tableCells'][0]['content'] = []
    result = docs.create_workout_document(exercises, 'Sheet', **services)
    assert result['documento_rigenerato'] == (damage != 'none')
    assert remote.create_calls == (1 if damage == 'none' else 2)


def test_saved_android_editor_refreshes_401_at_upload_not_whole_workflow(tmp_path):
    from google_auth_httplib2 import AuthorizedHttp
    from httplib2 import Response
    from kivy_app.platform_android import AndroidCredentialProvider
    from test_kivy_export import make_editor
    calls = []

    class Bridge:
        token = 'old'
        def get_access_token(self): return self.token
        def start_authorization(self): self.token = 'fresh'
        def get_status(self): return 'authorized'

    class Transport:
        def request(self, uri, method, body=None, headers=None, **kwargs):
            calls.append((method, body, headers['authorization']))
            return Response({'status': '401' if len(calls) == 1 else '200'}), b'{}'

    http = AuthorizedHttp(AndroidCredentialProvider(Bridge()).get_credentials(['scope']),
                          http=Transport(), max_refresh_attempts=1)
    editor = make_editor(tmp_path)
    editor._upload = lambda path: http.request('https://drive.test/file', 'PATCH', body=b'zip')
    editor.salva()
    assert calls == [('PATCH', b'zip', 'Bearer old'), ('PATCH', b'zip', 'Bearer fresh')]


def test_drive_permission_failure_never_regenerates(tmp_path, monkeypatch):
    remote = FakeGoogleDocState()
    state = tmp_path / 'state.json'
    docs.salva_stato(str(state), {'doc_id': remote.doc_id, 'esercizi': []})
    before = state.read_bytes()
    def denied(*args, **kwargs):
        raise _http_error(403)
    monkeypatch.setattr(FakeFilesResource, 'get', denied)
    with pytest.raises(docs.GoogleDocsError):
        docs.create_workout_document([], 'Sheet', docs_service=FakeDocsService(remote),
            drive_service=FakeDriveService(FakeDriveState()), state_path=str(state))
    assert remote.create_calls == 0
    assert state.read_bytes() == before


def test_explicit_regeneration_unblocks_uncertain_creation(tmp_path):
    state = tmp_path / 'state.json'
    docs.salva_stato(str(state), {'doc_id': None, 'esercizi': [], 'pending': {'phase': 'create'}})
    result = docs.create_workout_document([], 'Sheet',
        docs_service=FakeDocsService(FakeGoogleDocState()),
        drive_service=FakeDriveService(FakeDriveState()), state_path=str(state),
        force_regenerate=True)
    assert result['documento_rigenerato']
    assert docs.carica_stato(str(state))['status'] == 'completed'


@pytest.mark.parametrize('content', ['{', '[1]', '{"esercizi": []}'])
def test_invalid_checkpoint_requires_explicit_regeneration(tmp_path, content):
    state = tmp_path / 'state.json'
    state.write_text(content)
    remote = FakeGoogleDocState()
    services = dict(docs_service=FakeDocsService(remote),
                    drive_service=FakeDriveService(FakeDriveState()), state_path=str(state))
    with pytest.raises(docs.GoogleDocsError, match='Checkpoint'):
        docs.create_workout_document([], 'Sheet', **services)
    assert remote.create_calls == 0
    assert state.read_text() == content
    assert docs.create_workout_document([], 'Sheet', force_regenerate=True,
                                        **services)['documento_rigenerato']


def test_progress_counts_previously_checkpointed_exercises(tmp_path):
    from test_kivy_export import make_editor
    from kivy_app.export import DocExportController
    controller = DocExportController(make_editor(tmp_path))
    controller._state_path = str(tmp_path / 'state.json')
    controller._totale_sessione = 2
    docs.salva_stato(controller._state_path, {'doc_id': 'old', 'esercizi': [{'slug': 'a'}]})
    assert controller.progresso() == (1, 2)
    docs.salva_stato(controller._state_path,
                     {'doc_id': 'old', 'esercizi': [{'slug': 'a'}, {'slug': 'b'}]})
    assert controller.progresso() == (2, 2)


def test_transient_batch_response_is_never_replayed(tmp_path, monkeypatch):
    remote = FakeGoogleDocState()
    calls = []
    original = FakeDocumentsResource.batchUpdate
    def uncertain(self, documentId, body):
        calls.append(body)
        original(self, documentId, body)
        raise _http_error(503)
    monkeypatch.setattr(FakeDocumentsResource, 'batchUpdate', uncertain)
    with pytest.raises(docs.GoogleDocsError):
        docs.create_workout_document([], 'Sheet', docs_service=FakeDocsService(remote),
            drive_service=FakeDriveService(FakeDriveState()),
            state_path=str(tmp_path / 'state.json'))
    assert len(calls) == 1


def test_android_credentials_refresh_existing_transport_token():
    from kivy_app.platform_android import AndroidCredentialProvider

    class Bridge:
        token = 'old'
        def get_access_token(self):
            return self.token
        def get_status(self):
            return 'authorized'
        def start_authorization(self):
            self.token = 'new'

    provider = AndroidCredentialProvider(Bridge())
    credentials = provider.get_credentials(['scope'])
    credentials.refresh(None)
    assert credentials.token == 'new'


def test_read_retry_bounded_and_mutation_never_replayed(monkeypatch):
    from core.google_retry import safe_service
    monkeypatch.setattr('core.google_retry.time.sleep', lambda _: None)
    calls = []

    class Request:
        def execute(self):
            calls.append('execute')
            raise _http_error(503)

    class Resource:
        def get(self, **kwargs):
            return Request()
        def create(self, **kwargs):
            return Request()

    class Service:
        def files(self):
            return Resource()

    wrapped = safe_service(Service())
    with pytest.raises(Exception):
        wrapped.files().get(fileId='x').execute()
    assert len(calls) == 3
    calls.clear()
    with pytest.raises(Exception):
        wrapped.files().create(body={}).execute()
    assert len(calls) == 1
