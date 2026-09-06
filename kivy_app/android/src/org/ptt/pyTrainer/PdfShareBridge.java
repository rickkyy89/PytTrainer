package org.ptt.pyTrainer;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;

import androidx.core.content.FileProvider;

import java.io.File;

/** Shares private cached PDFs without ever exposing a file:// URI. */
public final class PdfShareBridge {
    private PdfShareBridge() { }

    public static void sharePdf(Activity activity, String path, String chooserTitle) {
        File file = new File(path);
        if (!file.isFile()) {
            throw new IllegalArgumentException("PDF does not exist: " + path);
        }
        String authority = activity.getPackageName() + ".fileprovider";
        Uri uri = FileProvider.getUriForFile(activity, authority, file);

        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType("application/pdf");
        send.putExtra(Intent.EXTRA_STREAM, uri);
        // ClipData is required for reliable temporary URI grants on API 24+
        // (including chooser forwarding and some mail/storage applications).
        send.setClipData(ClipData.newUri(
                activity.getContentResolver(), file.getName(), uri));
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);

        Intent chooser = Intent.createChooser(send, chooserTitle);
        chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        activity.startActivity(chooser);
    }
}
