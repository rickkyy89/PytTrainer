package org.ptt.spike;

import android.app.Activity;
import android.content.Intent;

import com.google.android.gms.auth.api.identity.AuthorizationClient;
import com.google.android.gms.auth.api.identity.AuthorizationRequest;
import com.google.android.gms.auth.api.identity.AuthorizationResult;
import com.google.android.gms.common.api.Scope;
import com.google.android.gms.tasks.OnFailureListener;
import com.google.android.gms.tasks.OnSuccessListener;
import com.google.android.gms.tasks.Task;

import org.kivy.android.PythonActivity;

import java.util.Arrays;

public final class GoogleBridge implements PythonActivity.ActivityResultListener {
    private static final int AUTH_REQUEST = 701;
    private static final int PICK_REQUEST = 702;
    private static GoogleBridge instance;
    private static volatile String status = "idle";
    private static volatile String accessToken = "";
    private static volatile String pickedUri = "";

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
        pickedUri = "";
        status = "authorizing";
        AuthorizationRequest request = AuthorizationRequest.builder()
                .setRequestedScopes(Arrays.asList(
                        new Scope("https://www.googleapis.com/auth/drive.file"),
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

    public static void openDrivePicker(Activity activity) {
        if (!"authorized".equals(status)) {
            status = "authorize_first";
            return;
        }
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/octet-stream");
        get(activity).activity.startActivityForResult(intent, PICK_REQUEST);
        status = "picker_open";
    }

    public static String getStatus() { return status; }
    public static int getTokenLength() { return accessToken.length(); }
    public static String getPickedUri() { return pickedUri; }
    public static String getAccessToken() { return accessToken; }

    @Override
    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == AUTH_REQUEST) {
            if (resultCode != Activity.RESULT_OK || data == null) {
                status = "authorization_cancelled";
                return;
            }
            try {
                handleAuthorization(authorizationClient.getAuthorizationResultFromIntent(data));
            } catch (Exception error) {
                status = "error: " + error.getClass().getSimpleName();
            }
            return;
        }
        if (requestCode == PICK_REQUEST) {
            if (resultCode == Activity.RESULT_OK && data != null && data.getData() != null) {
                pickedUri = data.getData().toString();
                status = "picked";
            } else {
                status = "picker_cancelled";
            }
            return;
        }
    }
}
