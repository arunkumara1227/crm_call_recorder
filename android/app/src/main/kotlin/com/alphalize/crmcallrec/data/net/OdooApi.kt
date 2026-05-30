package com.alphalize.crmcallrec.data.net

import com.squareup.moshi.JsonClass
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

/**
 * Mirrors c:\odoo19\custom_addons\crm_call_recorder\controllers\main.py:
 *   GET  /crm_call_recorder/ping
 *   POST /crm_call_recorder/upload  (multipart: phone, direction, duration, call_date, file)
 *
 * Auth headers (X-API-KEY, X-Odoo-Database) are injected by [ApiKeyInterceptor].
 */
interface OdooApi {

    @GET("crm_call_recorder/ping")
    suspend fun ping(): Response<PingResponse>

    @Multipart
    @POST("crm_call_recorder/upload")
    suspend fun upload(
        @Part("phone") phone: RequestBody,
        @Part("direction") direction: RequestBody,
        @Part("duration") duration: RequestBody,
        @Part("call_date") callDate: RequestBody,
        @Part("sim") sim: RequestBody,
        @Part file: MultipartBody.Part,
    ): Response<UploadResponse>
}

@JsonClass(generateAdapter = true)
data class PingResponse(
    val ok: Boolean,
    val server_time: String? = null,
    val error: String? = null,
)

@JsonClass(generateAdapter = true)
data class UploadResponse(
    val ok: Boolean,
    val id: Long? = null,
    val state: String? = null,
    val matched_partner_id: Long? = null,
    val matched_lead_id: Long? = null,
    val error: String? = null,
)
