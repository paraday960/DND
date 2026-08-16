package ir.paraday.dndbot

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File

class BotService : Service() {

    companion object {
        @Volatile
        var running = false
        private const val NOTIF_ID = 7
    }

    private var worker: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIF_ID, buildNotification())
        running = true

        if (wakeLock == null) {
            try {
                val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
                wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "dnd:server")
                wakeLock?.acquire()
            } catch (_: Exception) {
            }
        }

        if (worker == null || worker?.isAlive == false) {
            worker = Thread({ runBot() }, "dnd-bot").also { it.start() }
        }
        return START_STICKY
    }

    private fun runBot() {
        try {
            copyWebAsset()
            writeConfig()
            File(filesDir, "stop").delete()
            val py = Python.getInstance()
            py.getModule("android_bot").callAttr("main", filesDir.absolutePath)
        } catch (t: Throwable) {
            try {
                val f = File(filesDir, "bot.log")
                f.appendText("\n❌ خطای سرور: ${t.message}\n")
            } catch (_: Exception) {
            }
        } finally {
            running = false
            stopSelf()
        }
    }

    private fun writeConfig() {
        val p = getSharedPreferences("dnd", MODE_PRIVATE)
        val cfg = JSONObject().apply {
            put("BOT_TOKEN", p.getString("token", "") ?: "")
            put("AI_PROVIDER", p.getString("ai_provider", "mistral") ?: "mistral")
            put("AI_KEY", p.getString("ai_key", "") ?: "")
            put("AI_MODEL", p.getString("ai_model", "mistral-small-latest") ?: "mistral-small-latest")
            put("PORT", p.getString("port", "8080") ?: "8080".toIntOrNull() ?: 8080)
            put("DEV", false)
        }
        File(filesDir, "bot_config.json").writeText(cfg.toString())
    }

    private fun copyWebAsset() {
        val out = File(filesDir, "web/index.html")
        if (out.exists()) return
        out.parentFile?.mkdirs()
        assets.open("web/index.html").use { input ->
            out.outputStream().use { input.copyTo(it) }
        }
    }

    private fun buildNotification(): Notification {
        val chId = "dnd_server"
        if (Build.VERSION.SDK_INT >= 26) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(
                NotificationChannel(chId, "سرور D&D", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return if (Build.VERSION.SDK_INT >= 26) {
            Notification.Builder(this, chId)
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("🐉 سرور D&D روشن است")
                .setContentText("ربات و مینی‌گیم در حال اجرا هستند")
                .setContentIntent(pi)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("🐉 سرور D&D روشن است")
                .setContentText("ربات و مینی‌گیم در حال اجرا هستند")
                .setContentIntent(pi)
                .setOngoing(true)
                .build()
        }
    }

    override fun onDestroy() {
        try {
            File(filesDir, "stop").writeText("1")
        } catch (_: Exception) {
        }
        running = false
        try {
            wakeLock?.release()
        } catch (_: Exception) {
        }
        wakeLock = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
