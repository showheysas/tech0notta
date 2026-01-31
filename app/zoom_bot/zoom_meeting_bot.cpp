#include "zoom_meeting_bot.h"
#include "audio_raw_data_delegate.h"
#include <iostream>
#include <cstring>
#include <sstream>
#include <curl/curl.h>

ZoomMeetingBot::ZoomMeetingBot() 
{
}

ZoomMeetingBot::~ZoomMeetingBot()
{
    Cleanup();
}

bool ZoomMeetingBot::Initialize()
{
    if (m_isInitialized) return true;

    InitParam initParam;
    initParam.strWebDomain = "https://zoom.us";
    initParam.strSupportUrl = "https://zoom.us";
    initParam.enableLogByDefault = true;
    initParam.enableGenerateDump = true;
    
    SDKError err = ZOOM_SDK_NAMESPACE::InitSDK(initParam);
    if (err != SDKERR_SUCCESS) {
        std::cerr << "[ZoomBot] SDK Initialization Failed: " << err << std::endl;
        return false;
    }

    // Network connection helper
    INetworkConnectionHelper* pNetworkHelper = nullptr;
    CreateNetworkConnectionHelper(&pNetworkHelper);
    if (pNetworkHelper) {
        pNetworkHelper->RegisterNetworkConnectionHandler(this);
    }
    
    err = ZOOM_SDK_NAMESPACE::CreateAuthService(&m_pAuthService);
    if (err != SDKERR_SUCCESS || !m_pAuthService) {
        std::cerr << "[ZoomBot] Failed to create auth service: " << err << std::endl;
        return false;
    }
    m_pAuthService->SetEvent(this);

    err = ZOOM_SDK_NAMESPACE::CreateMeetingService(&m_pMeetingService);
    if (err != SDKERR_SUCCESS || !m_pMeetingService) {
        std::cerr << "[ZoomBot] Failed to create meeting service: " << err << std::endl;
        return false;
    }
    m_pMeetingService->SetEvent(this);

    m_isInitialized = true;
    std::cout << "[ZoomBot] SDK Initialized" << std::endl;
    return true;
}

void ZoomMeetingBot::Cleanup()
{
    StopRawAudioCapture();
    
    if (m_pAuthService) {
        m_pAuthService->SetEvent(nullptr);
        ZOOM_SDK_NAMESPACE::DestroyAuthService(m_pAuthService);
        m_pAuthService = nullptr;
    }
    if (m_pMeetingService) {
        m_pMeetingService->SetEvent(nullptr);
        ZOOM_SDK_NAMESPACE::DestroyMeetingService(m_pMeetingService);
        m_pMeetingService = nullptr;
    }
    
    ZOOM_SDK_NAMESPACE::CleanUPSDK();
    m_isInitialized = false;
    std::cout << "[ZoomBot] Cleanup done" << std::endl;
}

void ZoomMeetingBot::Start(const std::string& jwtToken, const std::string& meetingNumber, const std::string& password, const std::string& botName)
{
    m_jwtToken = jwtToken;
    m_meetingNumber = meetingNumber;
    m_password = password;
    m_botName = botName;
    
    std::cout << "[ZoomBot] Starting..." << std::endl;
    Authenticate();
}

void ZoomMeetingBot::Stop()
{
    StopRawAudioCapture();
    if (m_pMeetingService) {
        m_pMeetingService->Leave(LEAVE_MEETING);
    }
}

void ZoomMeetingBot::Authenticate()
{
    if (!m_pAuthService) return;

    AuthContext authContext;
    authContext.jwt_token = m_jwtToken.c_str();

    std::cout << "[ZoomBot] Requesting Authentication (Async)..." << std::endl;
    SDKError err = m_pAuthService->SDKAuth(authContext);
    if (err != SDKERR_SUCCESS) {
        std::cerr << "[ZoomBot] SDKAuth Failed: " << err << std::endl;
        QCoreApplication::exit(1);
    }
}

void ZoomMeetingBot::onAuthenticationReturn(AuthResult ret)
{
    std::cout << "[ZoomBot] Authentication Callback: " << ret << std::endl;
    
    if (ret == AUTHRET_SUCCESS) {
        std::cout << "[ZoomBot] Authentication Success! Joining meeting..." << std::endl;
        JoinMeeting();
    } else {
        std::cerr << "[ZoomBot] Authentication Failed." << std::endl;
        QCoreApplication::exit(1);
    }
}

void ZoomMeetingBot::JoinMeeting()
{
    if (!m_pMeetingService) return;

    JoinParam joinParam;
    joinParam.userType = SDK_UT_WITHOUT_LOGIN;

    JoinParam4WithoutLogin& param = joinParam.param.withoutloginuserJoin;
    param.meetingNumber = std::stoull(m_meetingNumber);
    param.vanityID = nullptr;
    param.userName = m_botName.c_str();
    param.psw = m_password.c_str();
    param.userZAK = nullptr;
    param.customer_key = nullptr;
    param.webinarToken = nullptr;
    param.isVideoOff = true;
    param.isAudioOff = false;

    std::cout << "[ZoomBot] Requesting Join Meeting (Async)..." << std::endl;
    SDKError err = m_pMeetingService->Join(joinParam);
    if (err != SDKERR_SUCCESS) {
        std::cerr << "[ZoomBot] Join Failed: " << err << std::endl;
        QCoreApplication::exit(1);
    }
}

void ZoomMeetingBot::onMeetingStatusChanged(MeetingStatus status, int iResult)
{
    std::cout << "[ZoomBot] Meeting Status Changed: " << status << " (Result: " << iResult << ")" << std::endl;

    if (status == MEETING_STATUS_INMEETING) {
        std::cout << "[ZoomBot] ✅ In Meeting! Connecting audio..." << std::endl;
        ConnectAudio();
        
        // 参加者コントローラーにイベントハンドラを登録
        IMeetingParticipantsController* participantCtrl = m_pMeetingService->GetMeetingParticipantsController();
        if (participantCtrl) {
            participantCtrl->SetEvent(this);
            std::cout << "[ZoomBot] 👥 Participant controller registered" << std::endl;
        }
        
        // 初期参加者リストを取得
        UpdateParticipantList();
        
        // Raw Audio キャプチャ開始
        StartRawAudioCapture();
        
        std::cout << "[ZoomBot] 🎧 Audio connected! Raw audio capture started." << std::endl;
        
    } else if (status == MEETING_STATUS_FAILED) {
        std::cerr << "[ZoomBot] Meeting Failed. Result: " << iResult << std::endl;
        QCoreApplication::exit(1);
    } else if (status == MEETING_STATUS_DISCONNECTING) {
        std::cout << "[ZoomBot] Meeting Disconnecting..." << std::endl;
        StopRawAudioCapture();
    } else if (status == MEETING_STATUS_ENDED) {
        std::cout << "[ZoomBot] Meeting Ended" << std::endl;
        StopRawAudioCapture();
        QCoreApplication::exit(0);
    }
}

void ZoomMeetingBot::ConnectAudio()
{
    if (!m_pMeetingService) return;
    IMeetingAudioController* audioCtrl = m_pMeetingService->GetMeetingAudioController();
    if (audioCtrl) {
        SDKError err = audioCtrl->JoinVoip();
        std::cout << "[ZoomBot] JoinVoip requested: " << err << std::endl;
        
        audioCtrl->MuteAudio(0, true);
        std::cout << "[ZoomBot] Audio muted (listen-only mode)" << std::endl;
    } else {
        std::cout << "[ZoomBot] Failed to get audio controller" << std::endl;
    }
}

void ZoomMeetingBot::StartRawAudioCapture()
{
    if (m_pAudioRawDataDelegate) {
        std::cout << "[ZoomBot] Raw audio capture already running" << std::endl;
        return;
    }

    // Raw Data Helper を取得
    m_pAudioRawDataHelper = GetAudioRawdataHelper();
    if (!m_pAudioRawDataHelper) {
        std::cerr << "[ZoomBot] Failed to get audio raw data helper" << std::endl;
        return;
    }

    // デリゲートを作成
    m_pAudioRawDataDelegate = new AudioRawDataDelegate(this, m_backendUrl);
    
    // デリゲートを登録
    // Note: setExternalAudioSource is for virtual mic. 
    // To receive audio, we just subscribe using the helper.
    
    // Raw Audio の購読を開始
    SDKError err = m_pAudioRawDataHelper->subscribe(m_pAudioRawDataDelegate);
    if (err != SDKERR_SUCCESS) {
        std::cerr << "[ZoomBot] Failed to subscribe to raw audio: " << err << std::endl;
        delete m_pAudioRawDataDelegate;
        m_pAudioRawDataDelegate = nullptr;
    } else {
        std::cout << "[ZoomBot] 🎤 Raw audio capture started (individual speakers)" << std::endl;
    }
}

void ZoomMeetingBot::StopRawAudioCapture()
{
    if (m_pAudioRawDataHelper && m_pAudioRawDataDelegate) {
        m_pAudioRawDataHelper->unSubscribe();
        std::cout << "[ZoomBot] Raw audio capture stopped" << std::endl;
    }
    
    if (m_pAudioRawDataDelegate) {
        m_pAudioRawDataDelegate->FlushAllBuffers();
        delete m_pAudioRawDataDelegate;
        m_pAudioRawDataDelegate = nullptr;
    }
    
    m_pAudioRawDataHelper = nullptr;
}

// === 参加者イベントハンドラ ===

void ZoomMeetingBot::onUserJoin(IList<unsigned int>* lstUserID, const zchar_t* strUserList)
{
    if (!lstUserID) return;
    
    IMeetingParticipantsController* participantCtrl = m_pMeetingService->GetMeetingParticipantsController();
    if (!participantCtrl) return;

    std::lock_guard<std::mutex> lock(m_participantsMutex);
    
    for (int i = 0; i < lstUserID->GetCount(); i++) {
        unsigned int userId = lstUserID->GetItem(i);
        IUserInfo* userInfo = participantCtrl->GetUserByUserID(userId);
        
        if (userInfo) {
            ParticipantInfo info;
            info.userId = userId;
            
            // ユーザー名を取得
            const zchar_t* name = userInfo->GetUserName();
            if (name) {
                // zchar_t is char on Linux
                info.userName = std::string(name);
            } else {
                info.userName = "Unknown";
            }
            
            info.isHost = userInfo->IsHost();
            info.isAudioMuted = userInfo->IsAudioMuted();
            
            m_participants[userId] = info;
            
            std::cout << "[ZoomBot] 👋 User joined: id=" << userId 
                      << " name=" << info.userName << std::endl;
            
            NotifyParticipantChange(userId, "join");
        }
    }
}

void ZoomMeetingBot::onUserLeft(IList<unsigned int>* lstUserID, const zchar_t* strUserList)
{
    if (!lstUserID) return;

    std::lock_guard<std::mutex> lock(m_participantsMutex);
    
    for (int i = 0; i < lstUserID->GetCount(); i++) {
        unsigned int userId = lstUserID->GetItem(i);
        
        auto it = m_participants.find(userId);
        if (it != m_participants.end()) {
            std::cout << "[ZoomBot] 👋 User left: id=" << userId 
                      << " name=" << it->second.userName << std::endl;
            
            NotifyParticipantChange(userId, "leave");
            m_participants.erase(it);
        }
    }
}


void ZoomMeetingBot::onUserNamesChanged(IList<unsigned int>* lstUserID)
{
    if (!lstUserID) return;
    
    IMeetingParticipantsController* participantCtrl = m_pMeetingService->GetMeetingParticipantsController();
    if (!participantCtrl) return;

    std::lock_guard<std::mutex> lock(m_participantsMutex);
    
    for (int i = 0; i < lstUserID->GetCount(); i++) {
        unsigned int userId = lstUserID->GetItem(i);
        IUserInfo* userInfo = participantCtrl->GetUserByUserID(userId);

        auto it = m_participants.find(userId);
        if (it != m_participants.end() && userInfo) {
            const zchar_t* name = userInfo->GetUserName();
            if (name) {
                std::string newName(name);
                
                if (it->second.userName != newName) {
                    it->second.userName = newName;
                    std::cout << "[ZoomBot] 📝 User name changed: id=" << userId 
                              << " name=" << newName << std::endl;
                    NotifyParticipantChange(userId, "name_change");
                }
            }
        }
    }
}

void ZoomMeetingBot::UpdateParticipantList()
{
    if (!m_pMeetingService) return;
    
    IMeetingParticipantsController* participantCtrl = m_pMeetingService->GetMeetingParticipantsController();
    if (!participantCtrl) return;

    IList<unsigned int>* participantList = participantCtrl->GetParticipantsList();
    if (!participantList) return;

    std::lock_guard<std::mutex> lock(m_participantsMutex);
    m_participants.clear();

    for (int i = 0; i < participantList->GetCount(); i++) {
        unsigned int userId = participantList->GetItem(i);
        IUserInfo* userInfo = participantCtrl->GetUserByUserID(userId);
        
        if (userInfo) {
            ParticipantInfo info;
            info.userId = userId;
            
            const zchar_t* name = userInfo->GetUserName();
            if (name) {
                info.userName = std::string(name);
            } else {
                info.userName = "Unknown";
            }
            
            info.isHost = userInfo->IsHost();
            info.isAudioMuted = userInfo->IsAudioMuted();
            
            m_participants[userId] = info;
            
            std::cout << "[ZoomBot] 👤 Participant: id=" << userId 
                      << " name=" << info.userName 
                      << (info.isHost ? " (Host)" : "") << std::endl;
        }
    }
    
    std::cout << "[ZoomBot] 📊 Total participants: " << m_participants.size() << std::endl;
}

std::map<unsigned int, ParticipantInfo> ZoomMeetingBot::GetParticipants() const
{
    std::lock_guard<std::mutex> lock(m_participantsMutex);
    return m_participants;
}

std::string ZoomMeetingBot::GetParticipantName(unsigned int userId) const
{
    std::lock_guard<std::mutex> lock(m_participantsMutex);
    
    auto it = m_participants.find(userId);
    if (it != m_participants.end()) {
        return it->second.userName;
    }
    return "Unknown";
}

void ZoomMeetingBot::NotifyParticipantChange(unsigned int userId, const std::string& action)
{
    if (m_backendUrl.empty()) return;
    
    // 参加者変更をバックエンドに通知（非同期推奨だがシンプル版として同期）
    std::string url = m_backendUrl + "/api/live/participant";
    
    CURL* curl = curl_easy_init();
    if (!curl) return;

    std::string userName = "";
    {
        auto it = m_participants.find(userId);
        if (it != m_participants.end()) {
            userName = it->second.userName;
        }
    }

    // JSON ペイロードを構築
    std::stringstream json;
    json << "{\"user_id\":" << userId 
         << ",\"user_name\":\"" << userName << "\""
         << ",\"action\":\"" << action << "\"}";
    std::string jsonStr = json.str();

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, jsonStr.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 2L);

    curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
}

// IMeetingRecordingCtrlEvent - 空実装
void ZoomMeetingBot::onRecordingStatus(RecordingStatus status)
{
    // Raw Audio キャプチャ方式では使用しない
}
