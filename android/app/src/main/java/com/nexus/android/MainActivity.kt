package com.nexus.android

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.tooling.preview.Preview
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

private val Navy = Color(0xFF07172B)
private val Panel = Color(0xFF10253C)
private val Green = Color(0xFF37D69A)
private val Orange = Color(0xFFFFA54A)
private val SoftWhite = Color(0xFFF2F6FA)
private val Muted = Color(0xFFAFBECE)

private data class SportsApp(
    val name: String,
    val region: String,
    val source: String,
    val url: String,
    val packageName: String? = null,
    val playStore: Boolean = false,
)

private val sportsApps = listOf(
    SportsApp("1xBet", "International", "Page officielle de l’application Android", "https://1xbet.com/en/mobile"),
    SportsApp("BetWinner", "International", "Page officielle de l’application Android", "https://betwinner.com/en/mobile"),
    SportsApp("MelBet", "International", "Centre d’applications officiel", "https://guidebook.melbet.com/app/"),
    SportsApp("Betway Ghana", "Ghana", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.betway.gh", "com.betway.gh", true),
    SportsApp("Betway Afrique du Sud", "Afrique du Sud", "Page officielle de téléchargement Android", "https://cdn.betway.co.za/Betway-App"),
    SportsApp("DraftKings", "États-Unis · selon l’État", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.draftkings.sportsbook", "com.draftkings.sportsbook", true),
    SportsApp("FanDuel", "États-Unis · selon l’État", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.fanduel.sportsbook", "com.fanduel.sportsbook", true),
    SportsApp("BetMGM", "États-Unis · selon l’État", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.playmgm.nj.sports", "com.playmgm.nj.sports", true),
    SportsApp("bet365", "Marchés sélectionnés", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.bet365SportsNJ.Bet365_ApplicationNJ", "com.bet365SportsNJ.Bet365_ApplicationNJ", true),
    SportsApp("Caesars Sportsbook", "États-Unis · selon l’État", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.williamhill.us.nj.sports", "com.williamhill.us.nj.sports", true),
    SportsApp("Fanatics Sports & Casino", "États-Unis · selon l’État", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.betfanatics.sportsbook.android", "com.betfanatics.sportsbook.android", true),
    SportsApp("BetRivers", "Marchés sélectionnés", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.rush.ri", "com.rush.ri", true),
    SportsApp("Betfair Sportsbook", "Marchés sélectionnés", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.betfair.sportsbook", "com.betfair.sportsbook", true),
    SportsApp("Paddy Power", "Marchés sélectionnés", "Google Play · éditeur officiel", "https://play.google.com/store/apps/details?id=com.paddypower.sportsbook.u.inhouse", "com.paddypower.sportsbook.u.inhouse", true),
)

class MainActivity : androidx.activity.ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                NexusSportsApp()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NexusSportsApp() {
    var selectedTab by remember { mutableIntStateOf(0) }
    Scaffold(
        containerColor = Navy,
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("NEXUS", color = SoftWhite, fontWeight = FontWeight.Black)
                        Text("SPORTS INTELLIGENCE", color = Green, style = MaterialTheme.typography.labelSmall)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Navy),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = Panel) {
                NavigationBarItem(
                    selected = selectedTab == 0,
                    onClick = { selectedTab = 0 },
                    icon = { Text("◎", color = if (selectedTab == 0) Green else Muted) },
                    label = { Text("Bookmakers") },
                )
                NavigationBarItem(
                    selected = selectedTab == 1,
                    onClick = { selectedTab = 1 },
                    icon = { Text("✦", color = if (selectedTab == 1) Orange else Muted) },
                    label = { Text("Nexus IA") },
                )
            }
        },
    ) { padding ->
        if (selectedTab == 0) {
            SportsCatalog(Modifier.padding(padding))
        } else {
            NexusAiConsole(Modifier.padding(padding))
        }
    }
}

@Composable
private fun SportsCatalog(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
    ) {
        item {
            Card(
                colors = CardDefaults.cardColors(containerColor = Panel),
                shape = RoundedCornerShape(20.dp),
            ) {
                Column(Modifier.padding(18.dp)) {
                    Text("Applications de paris sportifs", color = SoftWhite, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(6.dp))
                    Text("Accès Android aux bookmakers et à l’espace d’analyse Nexus.", color = Muted)
                    Spacer(Modifier.height(12.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(modifier = Modifier.size(9.dp), color = Green, shape = CircleShape) {}
                        Text("  Catalogue des sources officielles", color = Green, style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
        items(sportsApps) { app ->
            Card(
                colors = CardDefaults.cardColors(containerColor = Panel),
                shape = RoundedCornerShape(16.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Surface(modifier = Modifier.size(42.dp), color = Navy, shape = RoundedCornerShape(12.dp)) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(app.name.take(1), color = Orange, fontWeight = FontWeight.Black)
                        }
                    }
                    Column(Modifier.weight(1f)) {
                        Text(app.name, color = SoftWhite, fontWeight = FontWeight.SemiBold)
                        Text(app.region, color = Muted, style = MaterialTheme.typography.labelSmall)
                        Text(app.source, color = Muted, style = MaterialTheme.typography.labelSmall)
                    }
                    Button(
                        onClick = { openSportsApp(context, app) },
                        colors = ButtonDefaults.buttonColors(containerColor = Green, contentColor = Navy),
                    ) {
                        Text("Ouvrir / installer", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
        item {
            Text(
                "Les fiches et téléchargements dépendent du pays. Nexus ouvre les applications officielles; il ne passe pas de pari et ne manipule pas les comptes bookmaker.",
                color = Muted,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(vertical = 8.dp),
            )
        }
    }
}

private fun openSportsApp(context: android.content.Context, app: SportsApp) {
    if (app.packageName != null) {
        val launchIntent = context.packageManager.getLaunchIntentForPackage(app.packageName)
        if (launchIntent != null) {
            context.startActivity(launchIntent)
            return
        }
    }
    val uri = if (app.playStore && app.packageName != null) {
        Uri.parse("market://details?id=${app.packageName}")
    } else {
        Uri.parse(app.url)
    }
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, uri))
    } catch (_: ActivityNotFoundException) {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(app.url)))
    }
}

@Composable
private fun NexusAiConsole(modifier: Modifier = Modifier) {
    var webView by remember { mutableStateOf<WebView?>(null) }
    var canGoBack by remember { mutableStateOf(false) }
    BackHandler(enabled = canGoBack) { webView?.goBack() }

    Column(modifier.fillMaxSize()) {
        Text(
            "Console IA Nexus · GPT / Claude / Gemini",
            color = SoftWhite,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
        )
        AndroidView(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            factory = { context ->
                WebView(context).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    settings.loadsImagesAutomatically = true
                    webViewClient = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                            val host = request.url.host.orEmpty()
                            if (host == "nexus-deu3.onrender.com") return false
                            return try {
                                context.startActivity(Intent(Intent.ACTION_VIEW, request.url))
                                true
                            } catch (_: ActivityNotFoundException) {
                                true
                            }
                        }

                        override fun onPageFinished(view: WebView, url: String?) {
                            canGoBack = view.canGoBack()
                        }
                    }
                    loadUrl(BuildConfig.NEXUS_DASHBOARD_URL)
                    webView = this
                }
            },
            update = { view ->
                webView = view
                canGoBack = view.canGoBack()
            },
        )
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner, webView) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> webView?.onResume()
                Lifecycle.Event.ON_PAUSE -> webView?.onPause()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            webView?.stopLoading()
            webView?.destroy()
            webView = null
        }
    }
}

@Preview
@Composable
private fun NexusSportsPreview() {
    MaterialTheme { NexusSportsApp() }
}
