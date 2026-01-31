#ifndef AUDIO_RAW_DATA_DELEGATE_H
#define AUDIO_RAW_DATA_DELEGATE_H

#include "rawdata/zoom_rawdata_api.h"
#include "rawdata/rawdata_audio_helper_interface.h"
#include "zoom_sdk_raw_data_def.h"
#include <string>
#include <map>
#include <vector>
#include <mutex>
#include <functional>
#include <queue>
#include <memory>

using namespace ZOOM_SDK_NAMESPACE;

// Forward declaration
class ZoomMeetingBot;

/**
 * 話者ごとの音声バッファ
 */
struct SpeakerAudioBuffer {
    unsigned int userId;
    std::vector<char> audioData;
    uint64_t lastUpdateTime;
    size_t sampleRate;
    size_t channels;
};

/**
 * AudioRawDataDelegate - 個別参加者の音声を受信
 * 
 * IZoomSDKAudioRawDataDelegateを実装し、onOneWayAudioRawDataReceivedで
 * 各参加者の音声データを個別に受信する
 */
class AudioRawDataDelegate : public IZoomSDKAudioRawDataDelegate
{
public:
    AudioRawDataDelegate(ZoomMeetingBot* pBot, const std::string& backendUrl);
    virtual ~AudioRawDataDelegate();

    // IZoomSDKAudioRawDataDelegate インターフェース
    virtual void onMixedAudioRawDataReceived(AudioRawData* data) override;
    virtual void onOneWayAudioRawDataReceived(AudioRawData* data, unsigned int node_id) override;
    virtual void onShareAudioRawDataReceived(AudioRawData* data, unsigned int node_id) override;
    virtual void onOneWayInterpreterAudioRawDataReceived(AudioRawData* data, const zchar_t* pLanguageName) override {}

    // 音声データをバックエンドに送信
    void FlushAudioBuffer(unsigned int userId);
    void FlushAllBuffers();

    // 設定
    void SetSendIntervalMs(int ms) { m_sendIntervalMs = ms; }
    void SetMinBufferSize(size_t bytes) { m_minBufferSize = bytes; }

private:
    void SendAudioToBackend(unsigned int userId, const std::vector<char>& audioData);
    std::string GetParticipantName(unsigned int userId);

    ZoomMeetingBot* m_pBot;
    std::string m_backendUrl;
    
    // 話者ごとの音声バッファ (userId -> buffer)
    std::map<unsigned int, SpeakerAudioBuffer> m_audioBuffers;
    std::mutex m_bufferMutex;
    
    // 送信設定
    int m_sendIntervalMs = 500;      // 500ms間隔で送信
    size_t m_minBufferSize = 16000;  // 最小16KB（約0.5秒分）
};

#endif // AUDIO_RAW_DATA_DELEGATE_H
