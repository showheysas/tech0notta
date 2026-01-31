#include "audio_raw_data_delegate.h"
#include "zoom_meeting_bot.h"
#include <iostream>
#include <chrono>
#include <cstring>
#include <curl/curl.h>
#include <sstream>

AudioRawDataDelegate::AudioRawDataDelegate(ZoomMeetingBot* pBot, const std::string& backendUrl)
    : m_pBot(pBot)
    , m_backendUrl(backendUrl)
{
    std::cout << "[AudioDelegate] Created with backend URL: " << backendUrl << std::endl;
}

AudioRawDataDelegate::~AudioRawDataDelegate()
{
    FlushAllBuffers();
    std::cout << "[AudioDelegate] Destroyed" << std::endl;
}

void AudioRawDataDelegate::onMixedAudioRawDataReceived(AudioRawData* data)
{
    // 混合音声は使用しない（PulseAudioキャプチャと同等）
    // 個別話者音声のみを処理
}

void AudioRawDataDelegate::onOneWayAudioRawDataReceived(AudioRawData* data, unsigned int node_id)
{
    if (!data || !data->GetBuffer()) {
        return;
    }

    std::lock_guard<std::mutex> lock(m_bufferMutex);

    // 現在時刻を取得
    auto now = std::chrono::steady_clock::now();
    auto nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()
    ).count();

    // バッファを取得または作成
    auto it = m_audioBuffers.find(node_id);
    if (it == m_audioBuffers.end()) {
        SpeakerAudioBuffer buffer;
        buffer.userId = node_id;
        buffer.lastUpdateTime = nowMs;
        buffer.sampleRate = data->GetSampleRate();
        buffer.channels = data->GetChannelNum();
        m_audioBuffers[node_id] = buffer;
        it = m_audioBuffers.find(node_id);
        
        std::string userName = GetParticipantName(node_id);
        std::cout << "[AudioDelegate] 🎤 New speaker detected: userId=" << node_id 
                  << " name=" << userName << std::endl;
    }

    // 音声データをバッファに追加
    char* audioData = data->GetBuffer();
    unsigned int bufferLen = data->GetBufferLen();
    
    it->second.audioData.insert(
        it->second.audioData.end(),
        audioData,
        audioData + bufferLen
    );

    // 一定サイズまたは一定時間経過で送信
    bool shouldSend = false;
    if (it->second.audioData.size() >= m_minBufferSize) {
        shouldSend = true;
    } else if (nowMs - it->second.lastUpdateTime >= m_sendIntervalMs) {
        shouldSend = true;
    }

    if (shouldSend && !it->second.audioData.empty()) {
        // 送信用にコピー
        std::vector<char> dataToSend = std::move(it->second.audioData);
        it->second.audioData.clear();
        it->second.lastUpdateTime = nowMs;
        
        // ロックを解放してから送信
        lock.~lock_guard();
        SendAudioToBackend(node_id, dataToSend);
    }
}

void AudioRawDataDelegate::onShareAudioRawDataReceived(AudioRawData* data, unsigned int node_id)
{
    // 画面共有の音声は現時点では処理しない
}

void AudioRawDataDelegate::FlushAudioBuffer(unsigned int userId)
{
    std::lock_guard<std::mutex> lock(m_bufferMutex);
    
    auto it = m_audioBuffers.find(userId);
    if (it != m_audioBuffers.end() && !it->second.audioData.empty()) {
        std::vector<char> dataToSend = std::move(it->second.audioData);
        it->second.audioData.clear();
        
        lock.~lock_guard();
        SendAudioToBackend(userId, dataToSend);
    }
}

void AudioRawDataDelegate::FlushAllBuffers()
{
    std::lock_guard<std::mutex> lock(m_bufferMutex);
    
    for (auto& pair : m_audioBuffers) {
        if (!pair.second.audioData.empty()) {
            SendAudioToBackend(pair.first, pair.second.audioData);
            pair.second.audioData.clear();
        }
    }
}

std::string AudioRawDataDelegate::GetParticipantName(unsigned int userId)
{
    if (m_pBot) {
        return m_pBot->GetParticipantName(userId);
    }
    return "Unknown";
}

void AudioRawDataDelegate::SendAudioToBackend(unsigned int userId, const std::vector<char>& audioData)
{
    if (audioData.empty() || m_backendUrl.empty()) {
        return;
    }

    std::string participantName = GetParticipantName(userId);
    
    // バックエンドAPIエンドポイント
    std::string url = m_backendUrl + "/api/live/audio";

    std::cout << "[AudioDelegate] 📤 Sending audio: userId=" << userId 
              << " name=" << participantName
              << " size=" << audioData.size() << " bytes" << std::endl;

    // libcurlで送信（非同期送信が望ましいが、シンプル版として同期送信）
    CURL* curl = curl_easy_init();
    if (!curl) {
        std::cerr << "[AudioDelegate] Failed to initialize CURL" << std::endl;
        return;
    }

    // マルチパートフォームデータを構築
    curl_mime* mime = curl_mime_init(curl);
    curl_mimepart* part;

    // user_id
    part = curl_mime_addpart(mime);
    curl_mime_name(part, "user_id");
    std::string userIdStr = std::to_string(userId);
    curl_mime_data(part, userIdStr.c_str(), CURL_ZERO_TERMINATED);

    // user_name
    part = curl_mime_addpart(mime);
    curl_mime_name(part, "user_name");
    curl_mime_data(part, participantName.c_str(), CURL_ZERO_TERMINATED);

    // audio_data (binary)
    part = curl_mime_addpart(mime);
    curl_mime_name(part, "audio_data");
    curl_mime_data(part, audioData.data(), audioData.size());
    curl_mime_type(part, "audio/raw");

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_MIMEPOST, mime);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 5L);

    CURLcode res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        std::cerr << "[AudioDelegate] CURL error: " << curl_easy_strerror(res) << std::endl;
    }

    curl_mime_free(mime);
    curl_easy_cleanup(curl);
}
