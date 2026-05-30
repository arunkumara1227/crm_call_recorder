package com.alphalize.crmcallrec.data.net

import com.alphalize.crmcallrec.data.prefs.SecurePrefs
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Builds Retrofit lazily and rebuilds it whenever the server URL changes.
 * Exposes [api] as a StateFlow — UI/services collect it so they always see
 * the latest configured endpoint.
 */
class NetworkModule(private val prefs: SecurePrefs) {

    private val moshi: Moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    private val okHttp: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)
        .addInterceptor(ApiKeyInterceptor(prefs))
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        })
        .build()

    private val _api = MutableStateFlow<OdooApi?>(buildApi(prefs.config.value.serverUrl))
    val api: StateFlow<OdooApi?> = _api.asStateFlow()

    init {
        // Rebuild Retrofit when the server URL changes.
        // (Synchronous-collected here would block; instead just check on every getApi() call.)
    }

    /** Returns the current API client, rebuilding if the URL has changed. */
    fun currentApi(): OdooApi? {
        val url = prefs.config.value.serverUrl
        val current = _api.value
        if (current == null || baseUrlFor(url) != lastBuiltBaseUrl) {
            _api.value = buildApi(url)
        }
        return _api.value
    }

    private var lastBuiltBaseUrl: String = ""

    private fun buildApi(serverUrl: String): OdooApi? {
        val base = baseUrlFor(serverUrl) ?: return null
        lastBuiltBaseUrl = base
        return Retrofit.Builder()
            .baseUrl(base)
            .client(okHttp)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(OdooApi::class.java)
    }

    private fun baseUrlFor(serverUrl: String): String? {
        if (serverUrl.isBlank()) return null
        val trimmed = serverUrl.trim().trimEnd('/')
        return "$trimmed/"
    }
}
