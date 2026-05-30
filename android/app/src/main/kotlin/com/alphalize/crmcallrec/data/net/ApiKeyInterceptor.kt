package com.alphalize.crmcallrec.data.net

import com.alphalize.crmcallrec.data.prefs.SecurePrefs
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Adds X-API-KEY and (when set) X-Odoo-Database headers on every outbound request.
 * Reads the current config snapshot from [SecurePrefs] each call so a Settings save
 * takes effect on the next request without rebuilding Retrofit.
 */
class ApiKeyInterceptor(private val prefs: SecurePrefs) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val cfg = prefs.config.value
        val builder = chain.request().newBuilder()
        if (cfg.apiKey.isNotBlank()) {
            builder.header("X-API-KEY", cfg.apiKey)
        }
        if (cfg.database.isNotBlank()) {
            builder.header("X-Odoo-Database", cfg.database)
        }
        return chain.proceed(builder.build())
    }
}
