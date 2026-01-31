/**
 * @file audio_raw_data_handler.cpp
 * @brief 音声rawdataの処理と文字起こし連携
 */
#include <iostream>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <cstring>

/**
 * @brief 音声データをファイルに保存（デバッグ用）
 */
void saveAudioToFile(const char* data, size_t length, int sampleRate, const std::string& filename)
{
    std::ofstream file(filename, std::ios::binary | std::ios::app);
    if (file.is_open()) {
        file.write(data, length);
        file.close();
    }
}

/**
 * @brief 現在時刻を文字列で取得
 */
std::string getCurrentTimestamp()
{
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::stringstream ss;
    ss << std::put_time(std::localtime(&time), "%Y%m%d_%H%M%S");
    return ss.str();
}

/**
 * @brief 音声データ受信ハンドラー（サンプル実装）
 * 
 * このハンドラーは音声データを受信した時に呼ばれます。
 * 実際の文字起こし機能を実装する場合は、ここでWhisper APIなどに送信します。
 */
void handleAudioData(const char* data, size_t length, int sampleRate)
{
    static size_t totalBytes = 0;
    static int callCount = 0;
    
    totalBytes += length;
    callCount++;
    
    // 1秒ごとにログを出力（約32回の呼び出し = 32kHzで1秒分）
    if (callCount % 32 == 0) {
        std::cout << "[AudioHandler] 音声受信中: " 
                  << (totalBytes / 1024) << " KB, "
                  << "サンプルレート: " << sampleRate << " Hz" 
                  << std::endl;
    }
    
    // TODO: ここで音声データを文字起こしサービス（Whisperなど）に送信
    // 例:
    // whisperClient.sendAudio(data, length, sampleRate);
}
