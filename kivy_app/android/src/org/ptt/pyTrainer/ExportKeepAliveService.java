package org.ptt.pyTrainer;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/** Same-process foreground lifetime for the Python export worker.
 * Not sticky: a killed process must recover from its bundle, not replay writes.
 */
public final class ExportKeepAliveService extends Service {
    private PowerManager.WakeLock wakeLock;
    private static final String CHANNEL = "pytrainer-export";

    public static void start(Context context) {
        Intent intent = new Intent(context, ExportKeepAliveService.class);
        if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
        else context.startService(intent);
    }

    public static void stop(Context context) {
        context.stopService(new Intent(context, ExportKeepAliveService.class));
    }

    @Override public void onCreate() {
        super.onCreate();
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(new NotificationChannel(
                CHANNEL, "Esportazione scheda", NotificationManager.IMPORTANCE_LOW));
        }
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        startForeground(702, builder.setContentTitle("pyTrainer")
            .setContentText("Esportazione Google Doc in corso")
            .setSmallIcon(android.R.drawable.stat_sys_upload).setOngoing(true).build());
        PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pyTrainer:export");
        wakeLock.acquire(60 * 60 * 1000L);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        return START_NOT_STICKY;
    }

    @Override public void onDestroy() {
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        stopForeground(true);
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
