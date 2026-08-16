package ir.paraday.dndbot;

import android.app.*; import android.content.*; import android.os.*; import java.io.*; import org.json.JSONObject; import com.chaquo.python.Python; import com.chaquo.python.android.AndroidPlatform; import java.util.concurrent.atomic.AtomicBoolean;

public class BotService extends Service {
    static final int ID=77; Thread worker; PowerManager.WakeLock lock;
    static final AtomicBoolean RUNNING = new AtomicBoolean(false);
    @Override public int onStartCommand(Intent i,int flags,int id){
        try { startForeground(ID, notification()); } catch(Throwable t){ log("foreground: "+t); stopSelf(); return START_NOT_STICKY; }
        if(!RUNNING.compareAndSet(false,true)){
            File stop=new File(getFilesDir(),"stop");
            log(stop.exists() ? "⏳ نسخه قبلی در حال توقف است — چند ثانیه دیگر دوباره شروع کن" : "⚠️ ربات در حال اجراست — دکمه «توقف» را بزن");
            return START_STICKY;
        }
        worker=new Thread(this::run,"dnd-python"); worker.start();
        return START_STICKY;
    }
    void run(){
        try {
            writeConfig(); copyAsset();
            if(!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
            Python.getInstance().getModule("android_bot").callAttr("main", getFilesDir().getAbsolutePath(), getApplicationInfo().nativeLibraryDir);
        } catch(Throwable t){ log("CRASH: "+t); }
        finally { RUNNING.set(false); }
    }
    void writeConfig() throws Exception { SharedPreferences p=getSharedPreferences("dnd",MODE_PRIVATE); JSONObject o=new JSONObject(); o.put("BOT_TOKEN",p.getString("token","")); o.put("AI_PROVIDER","mistral"); o.put("AI_KEY",p.getString("ai_key","")); o.put("AI_MODEL","mistral-small-latest"); int port=8080; try{port=Integer.parseInt(p.getString("port","8080"));}catch(Exception ignored){} o.put("PORT",port); o.put("DEV",false); File f=new File(getFilesDir(),"bot_config.json"); try(FileWriter w=new FileWriter(f)){w.write(o.toString());} }
    void copyAsset() throws Exception { File f=new File(getFilesDir(),"web/index.html"); if(f.exists())return; f.getParentFile().mkdirs(); try(InputStream in=getAssets().open("web/index.html"); OutputStream out=new FileOutputStream(f)){byte[] b=new byte[8192];int n;while((n=in.read(b))>0)out.write(b,0,n);} }
    Notification notification(){ String ch="dnd"; if(Build.VERSION.SDK_INT>=26){NotificationManager n=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);n.createNotificationChannel(new NotificationChannel(ch,"D&D Server",NotificationManager.IMPORTANCE_LOW));} Notification.Builder b=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,ch):new Notification.Builder(this); return b.setSmallIcon(android.R.drawable.stat_notify_sync).setContentTitle("D&D Server فعال است").setContentText("ربات در حال اجراست").setOngoing(true).build(); }
    void log(String s){try{File f=new File(getFilesDir(),"bot.log");try(FileWriter w=new FileWriter(f,true)){w.write(s+"\n");}}catch(Exception ignored){}}
    @Override public void onDestroy(){
        // سیگنال توقف به پایتون: حلقه‌ها تمام می‌شوند، وب‌سرور پورت را آزاد می‌کند و تونل بسته می‌شود
        try{ new File(getFilesDir(),"stop").createNewFile(); }catch(Exception ignored){}
        if(worker!=null){ try{ worker.join(2500); }catch(Exception ignored){} }
        if(lock!=null)try{lock.release();}catch(Exception ignored){}
        super.onDestroy();
    }
    @Override public android.os.IBinder onBind(Intent i){return null;}
}
