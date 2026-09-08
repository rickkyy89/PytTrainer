package org.ptt.pyTrainer;

import android.Manifest;
import android.app.Activity;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.CursorLoader;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

/** Puts user bundles where a file manager can find them: the public
 *  Documents/Download folders (MediaStore on API 29+, direct write with the
 *  storage permission below).  Every failure comes back as an "ERR:" string so
 *  the Python side can surface a precise message instead of a Java stack. */
public final class StorageBridge {
    private StorageBridge() { }

    private static final String CARTELLA = "pyTrainer";
    private static final String MIME = "application/zip";

    /** Copy srcPath into <Documents|Download>/pyTrainer/nome, overwriting a
     *  previous copy we created. Returns the URI/path or "ERR: <motivo>". */
    public static String salvaFile(Activity activity, String srcPath, String nome, String kind) {
        try {
            File src = new File(srcPath);
            if (!src.isFile()) {
                return "ERR: file sorgente mancante: " + srcPath;
            }
            if (nome == null || nome.trim().isEmpty()) {
                return "ERR: nome del file mancante.";
            }
            boolean download = "download".equals(kind);
            if (Build.VERSION.SDK_INT >= 29) {
                return salvaMediaStore(activity, src, nome, download);
            }
            return salvaDiretto(activity, src, nome, download);
        } catch (Exception exc) {
            return "ERR: " + exc;
        }
    }

    /** Copy a content:// selection into destDir keeping its display name. */
    public static String copiaUri(Activity activity, String uriStr, String destDir) {
        InputStream in = null;
        OutputStream out = null;
        try {
            Uri uri = Uri.parse(uriStr);
            String nome = displayNome(activity, uri);
            if (nome == null || nome.trim().isEmpty()) {
                return "ERR: nome del file non trovato nell'URI.";
            }
            nome = new File(nome).getName();
            File dest = new File(new File(destDir), nome);
            in = activity.getContentResolver().openInputStream(uri);
            if (in == null) {
                return "ERR: impossibile aprire il file selezionato.";
            }
            out = new FileOutputStream(dest);
            copiain(in, out);
            return dest.getAbsolutePath();
        } catch (Exception exc) {
            return "ERR: " + exc;
        } finally {
            chiudi(in);
            chiudi(out);
        }
    }

    private static String salvaMediaStore(Activity activity, File src, String nome,
                                          boolean download) throws Exception {
        String base = download ? Environment.DIRECTORY_DOWNLOADS : Environment.DIRECTORY_DOCUMENTS;
        Uri collection = download
                ? MediaStore.Downloads.EXTERNAL_CONTENT_URI
                : MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL);
        Uri esistente = cercaUri(activity, collection, nome, base + "/" + CARTELLA + "/");
        if (esistente != null) {
            activity.getContentResolver().delete(esistente, null, null);
        }

        ContentValues valori = new ContentValues();
        valori.put(MediaStore.MediaColumns.DISPLAY_NAME, nome);
        valori.put(MediaStore.MediaColumns.MIME_TYPE, MIME);
        valori.put(MediaStore.MediaColumns.RELATIVE_PATH, base + "/" + CARTELLA);
        valori.put(MediaStore.MediaColumns.IS_PENDING, 1);

        Uri uri = activity.getContentResolver().insert(collection, valori);
        if (uri == null) {
            return "ERR: il sistema ha rifiutato il salvataggio in " + base + "/" + CARTELLA + ".";
        }
        InputStream in = null;
        OutputStream out = null;
        try {
            in = new FileInputStream(src);
            out = activity.getContentResolver().openOutputStream(uri, "w");
            if (out == null) {
                return "ERR: impossibile scrivere su " + uri + ".";
            }
            copiain(in, out);
        } finally {
            chiudi(in);
            chiudi(out);
        }
        valori.clear();
        valori.put(MediaStore.MediaColumns.IS_PENDING, 0);
        activity.getContentResolver().update(uri, valori, null, null);
        return uri.toString();
    }

    private static Uri cercaUri(Activity activity, Uri collection, String nome, String relativePath) {
        Cursor c = null;
        try {
            c = activity.getContentResolver().query(collection,
                    new String[]{MediaStore.MediaColumns._ID},
                    MediaStore.MediaColumns.DISPLAY_NAME + "=? AND "
                            + MediaStore.MediaColumns.RELATIVE_PATH + "=?",
                    new String[]{nome, relativePath}, null);
            if (c != null && c.moveToFirst()) {
                return ContentUris.withAppendedId(collection, c.getLong(0));
            }
        } catch (Exception ignored) {
            // nessun database MediaStore consultabile: si procedera' con insert
        } finally {
            if (c != null) c.close();
        }
        return null;
    }

    private static String salvaDiretto(Activity activity, File src, String nome, boolean download)
            throws Exception {
        if (activity.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED) {
            activity.requestPermissions(
                    new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, 41);
            return "ERR: permesso di archiviazione richiesto: concedilo e riprova il salvataggio.";
        }
        String base = download ? Environment.DIRECTORY_DOWNLOADS : Environment.DIRECTORY_DOCUMENTS;
        File dir = new File(Environment.getExternalStoragePublicDirectory(base), CARTELLA);
        if (!dir.isDirectory() && !dir.mkdirs()) {
            return "ERR: impossibile creare la cartella " + dir.getAbsolutePath() + ".";
        }
        File dest = new File(dir, nome);
        InputStream in = null;
        OutputStream out = null;
        try {
            in = new FileInputStream(src);
            out = new FileOutputStream(dest);
            copiain(in, out);
        } finally {
            chiudi(in);
            chiudi(out);
        }
        return dest.getAbsolutePath();
    }

    private static String displayNome(Activity activity, Uri uri) {
        Cursor c = null;
        try {
            c = activity.getContentResolver().query(uri,
                    new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null);
            if (c != null && c.moveToFirst()) {
                return c.getString(0);
            }
        } catch (Exception ignored) {
            // fallback sotto con il percorso grezzo
        } finally {
            if (c != null) c.close();
        }
        return uri.getLastPathSegment();
    }

    private static void copiain(InputStream in, OutputStream out) throws Exception {
        byte[] buffer = new byte[64 * 1024];
        int letto;
        while ((letto = in.read(buffer)) != -1) {
            out.write(buffer, 0, letto);
        }
        out.flush();
    }

    private static void chiudi(java.io.Closeable c) {
        if (c != null) {
            try {
                c.close();
            } catch (Exception ignored) {
            }
        }
    }
}
