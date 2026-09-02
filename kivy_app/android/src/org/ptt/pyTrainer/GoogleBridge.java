package org.ptt.pyTrainer;

import android.app.Activity;

import com.google.android.gms.auth.api.identity.AuthorizationClient;
import com.google.android.gms.auth.api.identity.AuthorizationRequest;
import com.google.android.gms.auth.api.identity.AuthorizationResult;
import com.google.android.gms.common.api.Scope;
import com.google.android.gms.tasks.OnFailureListener;
import com.google.android.gms.tasks.OnSuccessListener;
import com.google.android.gms.tasks.Task;

import org.kivy.android.PythonActivity;

import java.util.Arrays;

/** Native Google authorization bridge used by kivy_app.platform_android. */
public final class GoogleBridge implements PythonActivity.ActivityResultListener {
    private static final int AUTH_REQUEST = 701;
    private static GoogleBridge instance;
    private static volatile String status = "idle";
    private static volatile String accessToken = "";

    private final Activity activity;
    private final AuthorizationClient authorizationClient;

    private GoogleBridge(Activity activity) {
        this.activity = activity;
        authorizationClient = com.google.android.gms.auth.api.identity.Identity
                .getAuthorizationClient(activity);
        ((PythonActivity) activity).registerActivityResultListener(this);
    }

    private static GoogleBridge get(Activity activity) {
        if (instance == null) {
            instance = new GoogleBridge(activity);
        }
        return instance;
    }

    public static void startAuthorization(Activity activity) {
        final GoogleBridge bridge = get(activity);
        accessToken = "";
        status = "authorizing";
        AuthorizationRequest request = AuthorizationRequest.builder()
                .setRequestedScopes(Arrays.asList(
                        new Scope("https://www.googleapis.com/auth/drive"),
                        new Scope("https://www.googleapis.com/auth/documents")))
                .build();
        Task<AuthorizationResult> task = bridge.authorizationClient.authorize(request);
        task.addOnSuccessListener(new OnSuccessListener<AuthorizationResult>() {
            @Override
            public void onSuccess(AuthorizationResult result) {
                bridge.handleAuthorization(result);
            }
        });
        task.addOnFailureListener(new OnFailureListener() {
            @Override
            public void onFailure(Exception error) {
                status = "error: " + error.getClass().getSimpleName();
            }
        });
    }

    private void handleAuthorization(AuthorizationResult result) {
        if (result.hasResolution()) {
            status = "consent_required";
            try {
                activity.startIntentSenderForResult(
                        result.getPendingIntent().getIntentSender(), AUTH_REQUEST,
                        null, 0, 0, 0);
            } catch (Exception error) {
                status = "error: " + error.getClass().getSimpleName();
            }
            return;
        }
        setToken(result.getAccessToken());
    }

    private void setToken(String token) {
        if (token == null || token.length() == 0) {
            status = "error: empty_token";
            return;
        }
        accessToken = token;
        status = "authorized";
    }

    public static String getStatus() { return status; }
    public static String getAccessToken() { return accessToken; }

    @Override
    public void onActivityResult(int requestCode, int resultCode, android.content.Intent data) {
        if (requestCode != AUTH_REQUEST) {
            return;
        }
        if (resultCode != Activity.RESULT_OK || data == null) {
            status = "authorization_cancelled";
            return;
        }
        try {
            handleAuthorization(authorizationClient.getAuthorizationResultFromIntent(data));
        } catch (Exception error) {
            status = "error: " + error.getClass().getSimpleName();
        }
    }
}
