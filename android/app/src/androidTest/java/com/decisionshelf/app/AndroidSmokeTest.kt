package com.decisionshelf.app

import android.webkit.WebView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AndroidSmokeTest {
    @Test
    fun secretStoreRoundTripUsesAndroidKeystore() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                SecretStore.initialize(activity)
                SecretStore.set("instrumented-test", "private-value")
                assertEquals("private-value", SecretStore.get("instrumented-test"))
                SecretStore.delete("instrumented-test")
                assertEquals(null, SecretStore.get("instrumented-test"))
            }
        }
    }

    @Test
    fun embeddedPythonServesVueApp() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            val deadline = System.currentTimeMillis() + 30_000
            var loaded = false
            while (!loaded && System.currentTimeMillis() < deadline) {
                scenario.onActivity { activity ->
                    val webView = activity.findViewById<WebView>(R.id.decision_shelf_webview)
                    loaded = webView.url?.startsWith("http://127.0.0.1:") == true
                }
                if (!loaded) Thread.sleep(250)
            }
            assertTrue("Local FastAPI/Vue app did not load", loaded)
        }
    }
}
