"""
config.txt生成ユーティリティ
Zoom Meeting SDKに渡す設定ファイルを生成
"""
import os
from typing import Optional


def generate_config(
    meeting_number: str,
    jwt_token: str,
    meeting_password: str = "",
    recording_token: str = "",
    get_video: bool = True,
    get_audio: bool = True,
    send_video: bool = False,
    send_audio: bool = False
) -> str:
    """
    Zoom Meeting SDK用のconfig.txtを生成
    
    Args:
        meeting_number: 会議番号
        jwt_token: SDK JWT
        meeting_password: 会議パスワード
        recording_token: 録音トークン（オプション）
        get_video: ビデオ受信するか
        get_audio: オーディオ受信するか
        send_video: ビデオ送信するか
        send_audio: オーディオ送信するか
    
    Returns:
        config.txt の内容
    """
    config = f"""meeting_number: "{meeting_number}"
token: "{jwt_token}"
meeting_password: "{meeting_password}"
recording_token: "{recording_token}"
GetVideoRawData: "{'true' if get_video else 'false'}"
GetAudioRawData: "{'true' if get_audio else 'false'}"
SendVideoRawData: "{'true' if send_video else 'false'}"
SendAudioRawData: "{'true' if send_audio else 'false'}"
"""
    return config


def write_config_file(
    output_path: str,
    meeting_number: str,
    jwt_token: str,
    meeting_password: str = "",
    **kwargs
) -> None:
    """
    config.txtファイルを書き出し
    
    Args:
        output_path: 出力ファイルパス
        meeting_number: 会議番号
        jwt_token: SDK JWT
        meeting_password: 会議パスワード
        **kwargs: generate_configに渡す追加引数
    """
    config_content = generate_config(
        meeting_number=meeting_number,
        jwt_token=jwt_token,
        meeting_password=meeting_password,
        **kwargs
    )
    
    with open(output_path, 'w') as f:
        f.write(config_content)
    
    print(f"✅ config.txt生成完了: {output_path}")


if __name__ == "__main__":
    # テスト用
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python config_generator.py <meeting_number> <jwt_token> [password]")
        sys.exit(1)
    
    meeting_number = sys.argv[1]
    jwt_token = sys.argv[2]
    password = sys.argv[3] if len(sys.argv) > 3 else ""
    
    write_config_file(
        output_path="config.txt",
        meeting_number=meeting_number,
        jwt_token=jwt_token,
        meeting_password=password
    )
