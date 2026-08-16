package ir.paraday.dndbot;

import com.chaquo.python.android.PyApplication;

/**
 * PyApplication به‌صورت خودکار Python.start(new AndroidPlatform(context)) را
 * هنگام شروع برنامه صدا می‌زند — بدون آن، فراخوانی Python.getInstance()
 * با خطای «Cannot use GenericPlatform on Android» کرش می‌کند.
 */
public class App extends PyApplication {
}
