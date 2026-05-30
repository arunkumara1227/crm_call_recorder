package com.alphalize.crmcallrec

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.alphalize.crmcallrec.service.FileObserverService
import com.alphalize.crmcallrec.ui.settings.SettingsScreen
import com.alphalize.crmcallrec.ui.status.StatusScreen
import com.alphalize.crmcallrec.ui.theme.CrmCallRecorderTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            CrmCallRecorderTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    PermissionGate { AppShell() }
                }
            }
        }
    }
}

private data class Tab(val route: String, val labelResId: Int, val icon: androidx.compose.ui.graphics.vector.ImageVector)

private val tabs = listOf(
    Tab("status", R.string.nav_status, Icons.Filled.List),
    Tab("settings", R.string.nav_settings, Icons.Filled.Settings),
)

@Composable
private fun AppShell() {
    val navController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route

    Scaffold(
        bottomBar = {
            NavigationBar {
                tabs.forEach { tab ->
                    NavigationBarItem(
                        selected = currentRoute?.let {
                            backStack?.destination?.hierarchy?.any { it.route == tab.route } == true
                        } ?: false,
                        onClick = {
                            navController.navigate(tab.route) {
                                launchSingleTop = true
                                popUpTo(navController.graph.startDestinationId) { saveState = true }
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = null) },
                        label = { Text(stringResource(tab.labelResId)) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = "status",
            modifier = Modifier.padding(padding),
        ) {
            composable("status") { StatusScreen() }
            composable("settings") { SettingsScreen() }
        }
    }
}

private fun requiredPermissions(): Array<String> {
    val out = mutableListOf(
        Manifest.permission.READ_CALL_LOG,
        Manifest.permission.READ_PHONE_STATE,  // for SubscriptionManager — per-SIM filter
    )
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        out += Manifest.permission.READ_MEDIA_AUDIO
        out += Manifest.permission.POST_NOTIFICATIONS
    } else {
        out += Manifest.permission.READ_EXTERNAL_STORAGE
    }
    return out.toTypedArray()
}

private fun hasAllPermissions(context: Context): Boolean =
    requiredPermissions().all {
        context.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED
    }

@Composable
private fun PermissionGate(content: @Composable () -> Unit) {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(hasAllPermissions(context)) }

    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        granted = hasAllPermissions(context)
        if (granted) FileObserverService.start(context)
    }

    LaunchedEffect(granted) {
        if (granted) FileObserverService.start(context)
    }

    if (granted) {
        content()
    } else {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(stringResource(R.string.perm_rationale_title),
                style = MaterialTheme.typography.headlineSmall)
            Text(stringResource(R.string.perm_rationale_body),
                style = MaterialTheme.typography.bodyMedium)
            Button(onClick = { launcher.launch(requiredPermissions()) }) {
                Text(stringResource(R.string.perm_grant))
            }
        }
    }
}
