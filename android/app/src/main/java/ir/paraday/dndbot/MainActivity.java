package ir.paraday.dndbot;

import android.app.Activity;
import android.content.*;
import android.graphics.Color;
import android.os.*;
import android.view.Gravity;
import android.widget.*;
import java.io.*;

public class MainActivity extends Activity {
    EditText token, ai, port; TextView status, logView; SharedPreferences prefs; Handler handler = new Handler(Looper.getMainLooper());
    int pad(){ return (int)(16*getResources().getDisplayMetrics().density); }
    TextView label(String s){ TextView t=new TextView(this); t.setText(s); t.setTextColor(Color.LTGRAY); t.setPadding(0,12,0,4); return t; }
    @Override public void onCreate(Bundle b){ super.onCreate(b); prefs=getSharedPreferences("dnd",MODE_PRIVATE); build(); handler.postDelayed(new Runnable(){public void run(){refreshLog();handler.postDelayed(this,1500);}},500); }
    void build(){
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(pad(),pad(),pad(),pad()); root.setBackgroundColor(Color.rgb(15,18,25));
        TextView title=new TextView(this); title.setText("🐉 D&D Server 2.15"); title.setTextSize(24); title.setTextColor(Color.rgb(245,210,110)); title.setGravity(Gravity.CENTER); root.addView(title);
        status=new TextView(this); status.setText("آماده اجرا"); status.setTextColor(Color.WHITE); status.setGravity(Gravity.CENTER); root.addView(status);
        root.addView(label("توکن ربات تلگرام")); token=new EditText(this); token.setSingleLine(); token.setTextColor(Color.WHITE); token.setHint("123456:ABC..."); root.addView(token);
        root.addView(label("کلید AI اختیاری")); ai=new EditText(this); ai.setSingleLine(); ai.setTextColor(Color.WHITE); root.addView(ai);
        root.addView(label("پورت")); port=new EditText(this); port.setSingleLine(); port.setText("8080"); port.setTextColor(Color.WHITE); root.addView(port);
        LinearLayout row=new LinearLayout(this); row.setOrientation(LinearLayout.HORIZONTAL); Button start=new Button(this); start.setText("▶ شروع"); start.setOnClickListener(v->start()); Button stop=new Button(this); stop.setText("■ توقف"); stop.setOnClickListener(v->{stopService(new Intent(this,BotService.class));status.setText("در حال توقف...");}); row.addView(start,new LinearLayout.LayoutParams(0,-2,1)); row.addView(stop,new LinearLayout.LayoutParams(0,-2,1)); root.addView(row);
        LinearLayout logRow=new LinearLayout(this); logRow.setOrientation(LinearLayout.HORIZONTAL); Button copy=new Button(this); copy.setText("📋 کپی کامل لاگ"); copy.setOnClickListener(v->copyLog()); Button clear=new Button(this); clear.setText("پاک‌کردن"); clear.setOnClickListener(v->{try{new File(getFilesDir(),"bot.log").delete();refreshLog();}catch(Exception ignored){}}); logRow.addView(copy,new LinearLayout.LayoutParams(0,-2,1)); logRow.addView(clear,new LinearLayout.LayoutParams(0,-2,1)); root.addView(logRow);
        logView=new TextView(this); logView.setTextColor(Color.LTGRAY); logView.setTextSize(11); logView.setTextIsSelectable(true); logView.setPadding(8,8,8,8); ScrollView sc=new ScrollView(this); sc.addView(logView); root.addView(sc,new LinearLayout.LayoutParams(-1,0,1));
        setContentView(root); token.setText(prefs.getString("token","")); ai.setText(prefs.getString("ai_key","")); port.setText(prefs.getString("port","8080")); refreshLog();
    }
    void start(){ String tok=token.getText().toString().trim(); if(tok.length()<10){status.setText("توکن ربات را وارد کن");return;} prefs.edit().putString("token",tok).putString("ai_key",ai.getText().toString().trim()).putString("port",port.getText().toString().trim()).apply(); Intent i=new Intent(this,BotService.class); if(Build.VERSION.SDK_INT>=26)startForegroundService(i);else startService(i);status.setText("در حال راه‌اندازی..."); }
    String logText(){try{File f=new File(getFilesDir(),"bot.log");return f.exists()?read(f):"(لاگی ثبت نشده)";}catch(Exception e){return "خطا در خواندن لاگ: "+e;}}
    String read(File f)throws Exception{StringBuilder s=new StringBuilder();BufferedReader r=new BufferedReader(new FileReader(f));String l;while((l=r.readLine())!=null)s.append(l).append('\n');r.close();return s.toString();}
    void refreshLog(){if(logView!=null)logView.setText(logText());}
    void copyLog(){ClipboardManager c=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);c.setPrimaryClip(ClipData.newPlainText("DND server log",logText()));Toast.makeText(this,"لاگ کامل کپی شد؛ حالا اینجا Paste کن",Toast.LENGTH_SHORT).show();}
}
