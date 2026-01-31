#ifndef ZOOM_MEETING_BOT_H
#define ZOOM_MEETING_BOT_H

#include <iostream>
#include <string>
#include <functional>
#include <vector>
#include <map>
#include <mutex>

#include "zoom_sdk.h"
#include "meeting_service_components/meeting_audio_interface.h"
#include "meeting_service_components/meeting_participants_ctrl_interface.h"
#include "meeting_service_components/meeting_recording_interface.h"
#include "rawdata/zoom_rawdata_api.h"
#include "rawdata/rawdata_audio_helper_interface.h"
#include "auth_service_interface.h"
#include "meeting_service_interface.h"
#include "network_connection_handler_interface.h"

// Qt
#include <QObject>
#include <QCoreApplication>
#include <QTimer>

using namespace ZOOM_SDK_NAMESPACE;

// forward declaration
class AudioRawDataDelegate;

/**
 * 参加者情報構造体
 */
struct ParticipantInfo {
    unsigned int userId;
    std::string userName;
    bool isHost;
    bool isAudioMuted;
};

/**
 * ZoomMeetingBot - 話者特定対応版
 * 
 * 各参加者の音声を個別に取得し、話者を特定する機能を持つ
 */
class ZoomMeetingBot : public QObject,
                       public IAuthServiceEvent,
                       public IMeetingServiceEvent,
                       public INetworkConnectionHandler,
                       public IMeetingRecordingCtrlEvent,
                       public IMeetingParticipantsCtrlEvent  // 参加者イベント追加
{
    Q_OBJECT
    
public:
    ZoomMeetingBot();
    virtual ~ZoomMeetingBot();

    bool Initialize();
    void Cleanup();
    void Start(const std::string& jwtToken, const std::string& meetingNumber, const std::string& password, const std::string& botName);
    void Stop();
    
    // 参加者情報取得
    std::map<unsigned int, ParticipantInfo> GetParticipants() const;
    std::string GetParticipantName(unsigned int userId) const;

    // バックエンドURL設定
    void SetBackendUrl(const std::string& url) { m_backendUrl = url; }

protected:
    // IAuthServiceEvent
    virtual void onAuthenticationReturn(AuthResult ret) override;
    virtual void onLoginReturnWithReason(LOGINSTATUS ret, IAccountInfo* pAccountInfo, LoginFailReason reason) override {}
    virtual void onLogout() override {}
    virtual void onZoomIdentityExpired() override {}
    virtual void onZoomAuthIdentityExpired() override {}
    
    // IMeetingServiceEvent
    virtual void onMeetingStatusChanged(MeetingStatus status, int iResult = 0) override;
    virtual void onMeetingStatisticsWarningNotification(StatisticsWarningType type) override {}
    virtual void onMeetingParameterNotification(const MeetingParameter* meeting_param) override {}
    virtual void onSuspendParticipantsActivities() override {}
    virtual void onAICompanionActiveStatusChanged(bool active) {} 
    virtual void onAICompanionActiveChangeNotice(bool bActive) override {} 
    virtual void onMeetingTopicChanged(const zchar_t* sTopic) override {} 
    virtual void onMeetingFullToWatchLiveStream(const zchar_t* sLiveStreamUrl) override {} 

    // INetworkConnectionHandler
    virtual void onProxyDetectComplete() override {}
    virtual void onProxySettingNotification(IProxySettingHandler* handler) override {}
    virtual void onSSLCertVerifyNotification(ISSLCertVerificationHandler* handler) override {}
    virtual void onUserNetworkStatusChanged(MeetingComponentType type, ConnectionQuality level, unsigned int userId, bool uplink) override {}

    // IMeetingRecordingCtrlEvent
    virtual void onRecordingStatus(RecordingStatus status) override;
    virtual void onCloudRecordingStatus(RecordingStatus status) override {}
    virtual void onRecordPrivilegeChanged(bool bCanRec) override {}
    virtual void onCloudRecordingStorageFull(time_t gracePeriodDate) override {}
    virtual void onRequestCloudRecordingResponse(RequestStartCloudRecordingStatus status) override {}
    virtual void onStartCloudRecordingRequested(IRequestStartCloudRecordingHandler* handler) override {}
    virtual void onEnableAndStartSmartRecordingRequested(IRequestEnableAndStartSmartRecordingHandler* handler) override {}
    virtual void onSmartRecordingEnableActionCallback(ISmartRecordingEnableActionHandler* pHandler) override {}
    virtual void onLocalRecordingPrivilegeRequestStatus(RequestLocalRecordingStatus status) override {}
    virtual void onLocalRecordingPrivilegeRequested(IRequestLocalRecordingPrivilegeHandler* handler) override {}
    virtual void onTranscodingStatusChanged(TranscodingStatus status, const zchar_t* path) override {}

    // IMeetingParticipantsCtrlEvent - 参加者イベント
    virtual void onUserJoin(IList<unsigned int>* lstUserID, const zchar_t* strUserList = nullptr) override;
    virtual void onUserLeft(IList<unsigned int>* lstUserID, const zchar_t* strUserList = nullptr) override;
    virtual void onHostChangeNotification(unsigned int userId) override {}
    virtual void onLowOrRaiseHandStatusChanged(bool bLow, unsigned int userid) override {}
    virtual void onUserNamesChanged(IList<unsigned int>* lstUserID) override;
    virtual void onCoHostChangeNotification(unsigned int userId, bool isCoHost) override {}
    virtual void onInvalidReclaimHostkey() override {}
    virtual void onAllHandsLowered() override {}
    virtual void onLocalRecordingStatusChanged(unsigned int user_id, RecordingStatus status) override {}
    virtual void onAllowParticipantsRenameNotification(bool bAllow) override {}
    virtual void onAllowParticipantsUnmuteSelfNotification(bool bAllow) override {}
    virtual void onAllowParticipantsStartVideoNotification(bool bAllow) override {}
    virtual void onAllowParticipantsShareWhiteBoardNotification(bool bAllow) override {}
    virtual void onRequestLocalRecordingPrivilegeChanged(LocalRecordingRequestPrivilegeStatus status) override {}
    // virtual void onAllowParticipantsShareStatusNotification(bool bAllow) override {} // Removed - not in interface
    virtual void onInMeetingUserAvatarPathUpdated(unsigned int userID) override {}
    virtual void onParticipantProfilePictureStatusChange(bool bHidden) override {}
    virtual void onFocusModeStateChanged(bool bEnabled) override {}
    virtual void onFocusModeShareTypeChanged(FocusModeShareType type) override {}
    
    // Missing methods implementation
    virtual void onAllowParticipantsRequestCloudRecording(bool bAllow) override {}
    virtual void onBotAuthorizerRelationChanged(unsigned int authorizeUserID) override {}
    virtual void onVirtualNameTagStatusChanged(bool bOn, unsigned int userID) override {}
    virtual void onVirtualNameTagRosterInfoUpdated(unsigned int userID) override {}
    virtual void onGrantCoOwnerPrivilegeChanged(bool canGrantOther) override {}

private:
    void Authenticate();
    void JoinMeeting();
    void ConnectAudio();
    void StartRawAudioCapture();
    void StopRawAudioCapture();
    void UpdateParticipantList();
    void NotifyParticipantChange(unsigned int userId, const std::string& action);

    IAuthService* m_pAuthService = nullptr;
    IMeetingService* m_pMeetingService = nullptr;
    IZoomSDKAudioRawDataHelper* m_pAudioRawDataHelper = nullptr;
    AudioRawDataDelegate* m_pAudioRawDataDelegate = nullptr;
    
    std::string m_jwtToken;
    std::string m_meetingNumber;
    std::string m_password;
    std::string m_botName;
    std::string m_backendUrl;
    bool m_isInitialized = false;
    
    // 参加者マップ (userId -> ParticipantInfo)
    std::map<unsigned int, ParticipantInfo> m_participants;
    mutable std::mutex m_participantsMutex;
};

#endif // ZOOM_MEETING_BOT_H
