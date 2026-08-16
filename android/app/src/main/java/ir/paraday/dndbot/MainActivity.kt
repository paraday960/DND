package ir.paraday.dndbot

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.io.File

class MainActivity : Activity() {

    private lateinit var etToken: EditText
    private lateinit var etAi: EditText
    private lateinit var etPort: EditText
    private lateinit var tvStatus: TextView
    private lateinit var tvUrl: TextView
    private lateinit var tvLog: TextView
    private lateinit var btnStart: Button
    private lateinit var btnStop: Button

    private val handler = Handler(Looper.getMainLooper())
    private val refresh = object : Runnable {
        override fun run() {
            updateUi()
            handler.postDelayed(this, 1500)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        loadPrefs()
        handler.post(refresh)
        requestExtraPermissions()
    }

    override fun onDestroy() {
        handler.removeCallbacks(refresh)
        super.onDestroy()
    }

    private fun prefs() = getSharedPreferences("dnd", MODE_PRIVATE)

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun label(t: String) = TextView(this).apply {
        text = t
        textSize = 12f
        setTextColor(Color.rgb(210, 200, 170))
        setPadding(0, dp(12), 0, dp(4))
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(18), dp(16), dp(16))
            setBackgroundColor(Color.rgb(13, 16, 23))
        }

        root.addView(TextView(this).apply {
            text = "🐉 D&D Bot Server"
            textSize = 22f
            setTextColor(Color.rgb(242, 214, 124))
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
        })
        root.addView(TextView(this).apply {
            text = "با یک لمس، ربات و مینی‌گیم روی گوشی‌ات روشن می‌شود"
            textSize = 12f
            setTextColor(Color.rgb(150, 160, 180))
            gravity = Gravity.CENTER
            setPadding(0, dp(4), 0, dp(10))
        })

        tvStatus = TextView(this).apply {
            textSize = 15f
            gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, dp(8))
        }
        root.addView(tvStatus)

        root.addView(label("توکن ربات تلگرام (از @BotFather)"))
        etToken = EditText(this).apply {
            isSingleLine = true
            hint = "123456789:ABC..."
            setTextColor(Color.WHITE)
            setHintTextColor(Color.rgb(120, 130, 150))
        }
        root.addView(etToken)

        root.addView(label("کلید هوش مصنوعی (Mistral / Gemini / Groq)"))
        etAi = EditText(this).apply {
            isSingleLine = true
            hint = "کلید API"
            setTextColor(Color.WHITE)
            setHintTextColor(Color.rgb(120, 130, 150))
        }
        root.addView(etAi)

        root.addView(label("پورت سرور (پیش‌فرض: 8080)"))
        etPort = EditText(this).apply {
            isSingleLine = true
            inputType = InputType.TYPE_CLASS_NUMBER
            setText("8080")
            setTextColor(Color.WHITE)
        }
        root.addView(etPort)

        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        btnStart = Button(this).apply {
            text = "▶️ شروع سرور"
            setOnClickListener {
                savePrefs()
                startForegroundService(Intent(this@MainActivity, BotService::class.java))
            }
        }
        btnStop = Button(this).apply {
            text = "⏹ توقف"
            isEnabled = false
            setOnClickListener {
                stopService(Intent(this@MainActivity, BotService::class.java))
            }
        }
        row.addView(btnStart, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(btnStop, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        root.addView(row)

        root.addView(label("آدرس مینی‌گیم (برای دکمه بازی در ربات)"))
        tvUrl = TextView(this).apply {
            textSize = 12f
            text = "—"
            typeface = Typeface.MONOSPACE
            setTextColor(Color.rgb(120, 180, 255))
        }
        root.addView(tvUrl)
        root.addView(Button(this).apply {
            text = "📋 کپی آدرس مینی‌گیم"
            setOnClickListener { copyUrl() }
        })

        root.addView(label("لاگ سرور"))
        tvLog = TextView(this).apply {
            textSize = 10f
            typeface = Typeface.MONOSPACE
            setTextColor(Color.rgb(170, 185, 205))
            setBackgroundColor(Color.rgb(9, 11, 17))
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        val sc = ScrollView(this).apply { addView(tvLog) }
        root.addView(sc, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        setContentView(root)
    }

    private fun loadPrefs() {
        val p = prefs()
        etToken.setText(p.getString("token", ""))
        etAi.setText(p.getString("ai_key", ""))
        etPort.setText(p.getString("port", "8080"))
    }

    private fun savePrefs() {
        prefs().edit()
            .putString("token", etToken.text.toString().trim())
            .putString("ai_key", etAi.text.toString().trim())
            .putString("port", etPort.text.toString().trim())
            .apply()
    }

    private fun updateUi() {
        val running = BotService.running
        tvStatus.text = if (running) "● سرور روشن است — ربات آنلاین 🟢" else "○ سرور خاموش است"
        tvStatus.setTextColor(if (running) Color.rgb(110, 230, 150) else Color.rgb(230, 120, 120))
        btnStart.isEnabled = !running
        btnStop.isEnabled = running

        val urlFile = File(filesDir, "tunnel_url.txt")
        tvUrl.text = if (urlFile.exists()) urlFile.readText().trim() else "در حال آماده‌سازی تونل امن..."

        val logFile = File(filesDir, "bot.log")
        tvLog.text = if (logFile.exists()) logFile.readText().takeLast(5000) else "(لاگی نیست)"
    }

    private fun copyUrl() {
        val url = tvUrl.text.toString()
        if (url.startsWith("http")) {
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(ClipData.newPlainText("minigame", url))
            Toast.makeText(this, "📋 آدرس کپی شد", Toast.LENGTH_SHORT).show()
        }
    }

    private fun requestExtraPermissions() {
        if (Build.VERSION.SDK_INT >= 33) {
            try {
                requestPermissions(arrayOf("android.permission.POST_NOTIFICATIONS"), 1)
            } catch (_: Exception) {
            }
        }
        try {
            val pm = getSystemService(POWER_SERVICE) as PowerManager
            if (!pm.isIgnoringBatteryOptimizations(packageName)) {
                try {
                    startActivity(
                        Intent(
                            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:$packageName")
                        )
                    )
                } catch (_: Exception) {
                }
            }
        } catch (_: Exception) {
        }
    }
}
