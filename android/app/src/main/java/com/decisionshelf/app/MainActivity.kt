package com.decisionshelf.app

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.DownloadListener
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : ComponentActivity() {
    private lateinit var webView: WebView
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingDownloadUrl: String? = null

    private val openFile = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val uri = if (result.resultCode == Activity.RESULT_OK) result.data?.data else null
        fileCallback?.onReceiveValue(uri?.let { arrayOf(it) })
        fileCallback = null
    }

    private val createBackup = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/x-sqlite3")
    ) { uri ->
        val url = pendingDownloadUrl
        pendingDownloadUrl = null
        if (uri != null && url != null) downloadBackup(url, uri)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        SecretStore.initialize(applicationContext)
        webView = WebView(this).apply {
            id = R.id.decision_shelf_webview
            setBackgroundColor(Color.rgb(244, 239, 230))
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = true
            settings.setSupportZoom(false)
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val host = request.url.host
                    return if (host == "127.0.0.1" || host == "localhost") false
                    else {
                        startActivity(Intent(Intent.ACTION_VIEW, request.url))
                        true
                    }
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onShowFileChooser(
                    webView: WebView,
                    callback: ValueCallback<Array<Uri>>,
                    params: FileChooserParams,
                ): Boolean {
                    fileCallback?.onReceiveValue(null)
                    fileCallback = callback
                    val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "application/*"
                        putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("application/x-sqlite3", "application/octet-stream"))
                    }
                    openFile.launch(intent)
                    return true
                }
            }
            setDownloadListener(DownloadListener { url, _, _, _, _ ->
                if (url.contains("/api/backup/export")) {
                    pendingDownloadUrl = url
                    createBackup.launch("Decision-Shelf-backup.dsbackup")
                } else {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                }
            })
        }
        setContentView(webView)
        configureBackButton()
        startServer()
    }

    private fun startServer() {
        thread(name = "decision-shelf-bootstrap") {
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(this))
                val port = Python.getInstance()
                    .getModule("decision_shelf.mobile")
                    .callAttr("start_server", filesDir.absolutePath)
                    .toInt()
                runOnUiThread { webView.loadUrl("http://127.0.0.1:$port/") }
            } catch (error: Throwable) {
                runOnUiThread {
                    Toast.makeText(this, "启动失败：${error.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun configureBackButton() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val script = """
                    (() => {
                      const detail = { handled: false };
                      window.dispatchEvent(new CustomEvent('decision-shelf-back', { detail }));
                      return detail.handled;
                    })()
                """.trimIndent()
                webView.evaluateJavascript(script) { handled ->
                    when {
                        handled == "true" -> Unit
                        webView.canGoBack() -> webView.goBack()
                        else -> finish()
                    }
                }
            }
        })
    }

    private fun downloadBackup(url: String, destination: Uri) {
        thread(name = "decision-shelf-backup") {
            try {
                val connection = URL(url).openConnection() as HttpURLConnection
                connection.connectTimeout = 10_000
                connection.readTimeout = 60_000
                connection.inputStream.use { input ->
                    contentResolver.openOutputStream(destination, "w")!!.use { output ->
                        input.copyTo(output)
                    }
                }
                connection.disconnect()
                runOnUiThread { Toast.makeText(this, "备份已导出", Toast.LENGTH_SHORT).show() }
            } catch (error: Throwable) {
                runOnUiThread {
                    Toast.makeText(this, "导出失败：${error.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    override fun onDestroy() {
        fileCallback?.onReceiveValue(null)
        webView.stopLoading()
        webView.destroy()
        // The Python thread is daemon-backed and belongs to the Android process.
        // Keeping it alive across Activity recreation avoids duplicate servers.
        super.onDestroy()
    }
}
