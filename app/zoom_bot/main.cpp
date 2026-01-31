/**
 * @file main.cpp
 * @brief Zoom Meeting Bot エントリーポイント (Qt Event Loop / Async)
 * @description PulseAudioキャプチャ方式用のシンプル版
 */
#include <iostream>
#include <cstdlib>
#include <csignal>
#include <string>

#include <QApplication>
#include <QTimer>

#include "zoom_meeting_bot.h"

// グローバル変数
ZoomMeetingBot* g_pBot = nullptr;

void signalHandler(int signum)
{
    std::cout << "\n[Main] シグナル受信: " << signum << std::endl;
    if (g_pBot) {
        g_pBot->Stop();
    }
    QCoreApplication::quit();
}

std::string getEnvRequired(const char* name)
{
    const char* value = std::getenv(name);
    if (!value || strlen(value) == 0) {
        std::cerr << "[Main] ❌ 必須環境変数が未設定: " << name << std::endl;
        exit(1);
    }
    return std::string(value);
}

std::string getEnvOptional(const char* name, const std::string& defaultValue)
{
    const char* value = std::getenv(name);
    if (!value || strlen(value) == 0) {
        return defaultValue;
    }
    return std::string(value);
}

int main(int argc, char* argv[])
{
    // ログバッファリング無効化
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    QApplication app(argc, argv);
    
    std::cout << "========================================" << std::endl;
    std::cout << "  🤖 Tech Notta - Zoom Meeting Bot" << std::endl;
    std::cout << "  📝 PulseAudio Capture Mode" << std::endl;
    std::cout << "========================================" << std::endl;
    
    bool initOnly = false;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--init-only") {
            initOnly = true;
        }
    }
    
    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);
    
    ZoomMeetingBot bot;
    g_pBot = &bot;

    if (!bot.Initialize()) {
        return 1;
    }

    if (initOnly) {
        std::cout << "[Main] Init Only Mode" << std::endl;
        bot.Cleanup();
        return 0;
    }
    
    std::string jwtToken = getEnvRequired("JWT_TOKEN");
    std::string meetingNumber = getEnvRequired("MEETING_NUMBER");
    std::string password = getEnvOptional("PASSWORD", "");
    std::string botName = getEnvOptional("BOT_NAME", "Tech Bot");

    // メインスレッドでBotを開始（イベントループ内で実行されるようにTimerを使う）
    QTimer::singleShot(0, [&](){
        bot.Start(jwtToken, meetingNumber, password, botName);
    });
    
    // イベントループ開始（ここからSDKのメッセージポンプが回る）
    // 音声キャプチャはentrypoint.shで別プロセスとして起動
    return app.exec();
}
