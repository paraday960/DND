package ir.paraday.dndbot;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.*;

public class MainActivity extends Activity {
    EditText token, ai, port; TextView status;
    SharedPreferences prefs;
    int pad() { return (int)(16 * getResources().getDisplayMetrics().density); }
    @Override public void onCreate(Bundle b) {
        super.onCreate(b); prefs = getSharedPreferences("dnd", MODE_PRIVATE); build();
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
    }
    TextView label(String s) { TextView t=new TextView(this); t.setText(s); t.setTextColor(Color.LTGRAY); t.setPadding(0,12,0,4); return t; }
    void build() {
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(pad(),pad(),pad(),pad()); root.setBackgroundColor(Color.rgb(15,18,25));
        TextView title=new TextView(this); title.setText("🐉 D&D Server 2.0"); title.setTextSize(24); title.setTextColor(Color.rgb(245,210,110)); title.setGravity(Gravity.CENTER); root.addView(title);
        status=new TextView(this); status.setText("آماده اجرا"); status.setTextColor(Color.WHITE); status.setGravity(Gravity.CENTER); root.addView(status);
        root.addView(label("توکن ربات تلگرام")); token=new EditText(this); token.setSingleLine(); token.setTextColor(Color.WHITE); token.setHint("123456:ABC..."); root.addView(token);
        root.addView(label("کلید AI اختیاری")); ai=new EditText(this); ai.setSingleLine(); ai.setTextColor(Color.WHITE); root.addView(ai);
        root.addView(label("پورت")); port=new EditText(this); port.setSingleLine(); port.setText("8080"); port.setTextColor(Color.WHITE); root.addView(port);
        LinearLayout row=new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL);
        Button start=new Button(this); start.setText("▶ شروع"); start.setOnClickListener(v -> start());
        Button stop=new Button(this); stop.setText("■ توقف"); stop.setOnClickListener(v -> stopService(new Intent(this,BotService.class)));
        row.addView(start,new LinearLayout.LayoutParams(0,-2,1)); row.addView(stop,new LinearLayout.LayoutParams(0,-2,1)); root.addView(row);
        TextView info=new TextView(this); info.setText("\nپس از شروع، برنامه را نبند؛ سرویس در پس‌زمینه فعال می‌ماند.\nلاگ: /Android/data/ir.paraday.dndbot/files/bot.log"); info.setTextColor(Color.GRAY); root.addView(info);
        setContentView(root);
        token.setText(prefs.getString("token","")); ai.setText(prefs.getString("ai_key","")); port.setText(prefs.getString("port","8080"));
    }
    void start() {
        String tok=token.getText().toString().trim(); if(tok.length()<10){ status.setText("توکن ربات را وارد کن"); return; }
        prefs.edit().putString("token",tok).putString("ai_key",ai.getText().toString().trim()).putString("port",port.getText().toString().trim()).apply();
        Intent i=new Intent(this,BotService.class); if(Build.VERSION.SDK_INT>=26) startForegroundService(i); else startService(i); status.setText("در حال راه‌اندازی...");
    }
}
