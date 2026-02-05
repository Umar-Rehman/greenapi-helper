import requests
from functools import lru_cache
from typing import Optional, Tuple

# Configuration

VERIFY_TLS = True
TIMEOUT_SECONDS = 60

# Certificate files for fallback (if not using credential manager)
_fallback_cert_files: Optional[Tuple[str, str]] = None


def set_certificate_files(cert_path: str, key_path: str):
    """Set certificate files to use for API calls."""
    global _fallback_cert_files
    _fallback_cert_files = (cert_path, key_path)
    # Clear cache when certificates change
    get_certificate_files.cache_clear()


@lru_cache(maxsize=1)
def get_certificate_files() -> Tuple[str, str]:
    """Get certificate files, using fallback if credential manager not set.

    Cached to avoid repeated file system checks.
    """
    if _fallback_cert_files:
        return _fallback_cert_files

    # Fallback to default files if they exist
    return ("client.crt", "client.key")


# Helper Functions


def _build_url(api_url: str, instance_id: str, path: str) -> str:
    return f"{api_url}/waInstance{instance_id}/{path}"


def is_max_instance(api_url: str) -> bool:
    """Check if this is a MAX instance based on /v3 path in API URL.

    Returns True for MAX instances (url contains /v3), False for WhatsApp instances.
    """
    return "/v3" in api_url


def send_request(
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    cert_files: Optional[Tuple[str, str]] = None,
    use_cert: bool = False,
) -> str:
    """Send an HTTP request with optional client certificate authentication.

    Args:
        method: HTTP method
        url: Request URL
        json_body: Optional JSON payload
        cert_files: Optional tuple of (cert_path, key_path). If None, uses configured certificates.
                   key_path can be None if only certificate is available.
        use_cert: Whether to use client certificate. Green API calls don't need certs (token auth only).

    Returns:
        Response text or error message
    """
    cert = None
    if use_cert:
        cert = cert_files or get_certificate_files()

        # Handle case where key_path might be None
        if cert and len(cert) == 2 and cert[1] is None:
            # If no key path, just use the cert path - requests will handle it
            cert = cert[0]

    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers={"accept": "application/json"},
            json=json_body,
            cert=cert,
            verify=VERIFY_TLS,
            timeout=TIMEOUT_SECONDS,
        )

        if resp.status_code != 200:
            return f"HTTP {resp.status_code}: {resp.text}"

        return resp.text

    except requests.exceptions.SSLError as e:
        return f"SSL Certificate Error: {str(e)}\nPlease check your client certificate."
    except requests.exceptions.RequestException as e:
        return f"Request Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def make_api_call(
    api_url: str,
    instance_id: str,
    api_token: str,
    path: str,
    method: str,
    json_body=None,
    query_params=None,
    cert_files: Optional[Tuple[str, str]] = None,
) -> str:
    """Make a generic API call to the Green API.

    Args:
        api_url: Base API URL.
        instance_id: WhatsApp instance ID.
        api_token: API token for authentication.
        path: API endpoint path (without token).
        method: HTTP method (GET, POST, etc.).
        json_body: Optional JSON payload for POST requests.
        query_params: Optional dict of query parameters.
        cert_files: Optional tuple of (cert_path, key_path) for client certificates.

    Returns:
        API response as string.
    """
    url = _build_url(api_url, instance_id, f"{path}/{api_token}")
    if query_params:
        from urllib.parse import urlencode

        url += "?" + urlencode(query_params)
    # Green API uses token authentication, not client certificates
    return send_request(method, url, json_body=json_body, cert_files=cert_files, use_cert=False)


# Account API functions


def get_instance_state(api_url: str, instance_id: str, api_token: str) -> str:
    """Get the current state of a WhatsApp instance."""
    return make_api_call(api_url, instance_id, api_token, "getStateInstance", "GET")


def get_instance_settings(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getSettings", "GET")


def set_instance_settings(api_url: str, instance_id: str, api_token: str, settings: dict) -> str:
    """Update the settings for a WhatsApp instance."""
    return make_api_call(api_url, instance_id, api_token, "setSettings", "POST", json_body=settings)


def logout_instance(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "logout", "GET")


def reboot_instance(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "reboot", "GET")


def get_qr_code(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "qr", "GET")


def get_authorization_code(api_url: str, instance_id: str, api_token: str, phone_number: int) -> str:
    """Get authorization code for a phone number (WhatsApp instances only).

    Sends POST with {"phoneNumber": <int>} (no + or 00 prefix).
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getAuthorizationCode",
        "POST",
        json_body={"phoneNumber": int(phone_number)},
    )


def update_api_token(api_url: str, instance_id: str, api_token: str) -> str:
    """Update/regenerate the API token for this instance (WhatsApp instances only).

    Returns new API token in response.
    """
    return make_api_call(api_url, instance_id, api_token, "updateApiToken", "GET")


def get_account_settings(api_url: str, instance_id: str, api_token: str) -> str:
    """Get account settings for WhatsApp or MAX instance.

    For WhatsApp instances: calls getWASettings
    For MAX instances: calls getAccountSettings
    """
    endpoint = "getAccountSettings" if is_max_instance(api_url) else "getWASettings"
    return make_api_call(api_url, instance_id, api_token, endpoint, "GET")


def get_contacts(api_url: str, instance_id: str, api_token: str) -> str:
    """Retrieve the contact list for the instance.

    Returns a JSON array of contacts as provided by the Green API.
    """
    return make_api_call(api_url, instance_id, api_token, "getContacts", "GET")


def check_whatsapp(api_url: str, instance_id: str, api_token: str, phone_number: int) -> str:
    """Check whether a phone number has WhatsApp.

    Sends a POST to the checkWhatsapp endpoint with JSON body {"phoneNumber": <int>}.
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "checkWhatsapp",
        "POST",
        json_body={"phoneNumber": int(phone_number)},
    )


def check_max(api_url: str, instance_id: str, api_token: str, phone_number: int, force: bool = False) -> str:
    """Check whether a phone number has MAX account (MAX instances only).

    Sends a POST to the checkAccount endpoint with JSON body {"phoneNumber": <int>, "force": <bool>}.
    force=False uses cached data (default), force=True queries MAX server directly.
    """
    body = {"phoneNumber": int(phone_number)}
    if force:
        body["force"] = True
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "checkAccount",
        "POST",
        json_body=body,
    )


# Journal API functions


def get_incoming_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "lastIncomingMessages",
        "GET",
        query_params={"minutes": minutes},
    )


def get_outgoing_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "lastOutgoingMessages",
        "GET",
        query_params={"minutes": minutes},
    )


def get_chat_history(api_url: str, instance_id: str, api_token: str, chat_id: str, count: int = 10) -> str:
    """Retrieve chat history for a specific chat."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getChatHistory",
        "POST",
        json_body={"chatId": chat_id, "count": count},
    )


def get_message(api_url: str, instance_id: str, api_token: str, chat_id: str, id_message: str) -> str:
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getMessage",
        "POST",
        json_body={"chatId": chat_id, "idMessage": id_message},
    )


def get_contact_info(api_url: str, instance_id: str, api_token: str, chat_id: str) -> str:
    """Retrieve detailed contact information for a chat.

    The API expects a JSON body: {"chatId": "<phoneWithCountryCode>@c.us"}.
    Example chat_id: '79876543210@c.us'.
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "GetContactInfo",
        "POST",
        json_body={"chatId": chat_id},
    )


def get_avatar(api_url: str, instance_id: str, api_token: str, chat_id: str) -> str:
    """Get avatar (profile picture) for a contact or group."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getAvatar",
        "POST",
        json_body={"chatId": chat_id},
    )


def edit_message(api_url: str, instance_id: str, api_token: str, chat_id: str, id_message: str, message: str) -> str:
    """Edit a previously sent message."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "editMessage",
        "POST",
        json_body={"chatId": chat_id, "idMessage": id_message, "message": message},
    )


def delete_message(
    api_url: str, instance_id: str, api_token: str, chat_id: str, id_message: str, only_sender_delete: bool = False
) -> str:
    """Delete a message.

    Args:
        only_sender_delete: If True, delete only for sender. If False, delete for everyone.
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "deleteMessage",
        "POST",
        json_body={"chatId": chat_id, "idMessage": id_message, "onlySenderDelete": only_sender_delete},
    )


def archive_chat(api_url: str, instance_id: str, api_token: str, chat_id: str) -> str:
    """Archive a chat."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "archiveChat",
        "POST",
        json_body={"chatId": chat_id},
    )


def unarchive_chat(api_url: str, instance_id: str, api_token: str, chat_id: str) -> str:
    """Unarchive a chat."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "unarchiveChat",
        "POST",
        json_body={"chatId": chat_id},
    )


def set_disappearing_chat(
    api_url: str, instance_id: str, api_token: str, chat_id: str, ephemeral_expiration: int
) -> str:
    """Set disappearing messages for a chat.

    Args:
        ephemeral_expiration: Time in seconds. Possible values: 0 (off),
            86400 (1 day), 604800 (7 days), 7776000 (90 days)
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "setDisappearingChat",
        "POST",
        json_body={"chatId": chat_id, "ephemeralExpiration": ephemeral_expiration},
    )


def mark_message_as_read(api_url: str, instance_id: str, api_token: str, chat_id: str, id_message: str) -> str:
    """Mark a specific message as read."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "readChat",
        "POST",
        json_body={"chatId": chat_id, "idMessage": id_message},
    )


def mark_chat_as_read(api_url: str, instance_id: str, api_token: str, chat_id: str) -> str:
    """Mark all messages in a chat as read."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "readChat",
        "POST",
        json_body={"chatId": chat_id},
    )


# Sending API functions


def send_message(
    api_url: str, instance_id: str, api_token: str, chat_id: str, message: str, quoted_message_id: str = None
) -> str:
    """Send a text message, optionally as a reply to another message.

    Args:
        chat_id: Chat ID to send to
        message: Text message to send
        quoted_message_id: Optional message ID to quote/reply to
    """
    body = {"chatId": chat_id, "message": message}
    if quoted_message_id:
        body["quotedMessageId"] = quoted_message_id

    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendMessage",
        "POST",
        json_body=body,
    )


def send_file_by_url(
    api_url: str,
    instance_id: str,
    api_token: str,
    chat_id: str,
    url_file: str,
    file_name: str,
    caption: str = "",
) -> str:
    """Send a file (image, video, audio, document) by URL.

    Args:
        chat_id: Chat ID to send to
        url_file: URL of the file to send
        file_name: Name for the file
        caption: Optional caption
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendFileByUrl",
        "POST",
        json_body={
            "chatId": chat_id,
            "urlFile": url_file,
            "fileName": file_name,
            "caption": caption,
        },
    )


def send_poll(
    api_url: str,
    instance_id: str,
    api_token: str,
    chat_id: str,
    message: str,
    options: list[str],
    multiple_answers: bool = False,
) -> str:
    """Send a poll.

    Args:
        chat_id: Chat ID to send to
        message: Poll question
        options: List of option strings
        multiple_answers: Whether to allow multiple selections
    """
    options_formatted = [{"optionName": opt} for opt in options]

    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendPoll",
        "POST",
        json_body={
            "chatId": chat_id,
            "message": message,
            "options": options_formatted,
            "multipleAnswers": multiple_answers,
        },
    )


def send_location(
    api_url: str,
    instance_id: str,
    api_token: str,
    chat_id: str,
    latitude: float,
    longitude: float,
    name_location: str = "",
    address: str = "",
) -> str:
    """Send a location.

    Args:
        chat_id: Chat ID to send to
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        name_location: Optional location name
        address: Optional address
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendLocation",
        "POST",
        json_body={
            "chatId": chat_id,
            "nameLocation": name_location,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
        },
    )


def send_contact(
    api_url: str,
    instance_id: str,
    api_token: str,
    chat_id: str,
    phone_contact: int,
    first_name: str,
    middle_name: str = "",
    last_name: str = "",
    company: str = "",
) -> str:
    """Send a contact card.

    Args:
        chat_id: Chat ID to send to
        phone_contact: Phone number
        first_name: First name
        middle_name: Optional middle name
        last_name: Optional last name
        company: Optional company name
    """
    contact = {
        "phoneContact": phone_contact,
        "firstName": first_name,
    }
    if middle_name:
        contact["middleName"] = middle_name
    if last_name:
        contact["lastName"] = last_name
    if company:
        contact["company"] = company

    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendContact",
        "POST",
        json_body={"chatId": chat_id, "contact": contact},
    )


def forward_messages(
    api_url: str,
    instance_id: str,
    api_token: str,
    chat_id: str,
    chat_id_from: str,
    messages: list[str],
) -> str:
    """Forward messages from one chat to another.

    Args:
        chat_id: Destination chat ID
        chat_id_from: Source chat ID
        messages: List of message IDs to forward
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "forwardMessages",
        "POST",
        json_body={
            "chatId": chat_id,
            "chatIdFrom": chat_id_from,
            "messages": messages,
        },
    )


# Queue API functions


def get_msg_queue_count(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getMessagesCount", "GET")


def get_msg_queue(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "showMessagesQueue", "GET")


def clear_msg_queue_to_send(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "clearMessagesQueue", "GET")


def get_webhook_count(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getWebhooksCount", "GET")


def clear_webhooks_queue(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "clearWebhooksQueue", "DELETE")


# Status API functions


def get_outgoing_statuses(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getOutgoingStatuses",
        "GET",
        query_params={"minutes": minutes},
    )


def get_incoming_statuses(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getIncomingStatuses",
        "GET",
        query_params={"minutes": minutes},
    )


def get_status_statistic(api_url: str, instance_id: str, api_token: str, id_message: str) -> str:
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getStatusStatistic",
        "GET",
        query_params={"idMessage": id_message},
    )


def send_text_status(
    api_url: str,
    instance_id: str,
    api_token: str,
    message: str,
    background_color: str = "#228B22",
    font: str = "SERIF",
    participants: list[str] = None,
) -> str:
    """Send a text status.

    Args:
        message: Status text message
        background_color: Background color in hex format (default: #228B22)
        font: Font style (SERIF, SANS_SERIF, etc.)
        participants: List of chat IDs who can see the status (optional)
    """
    payload = {
        "message": message,
        "backgroundColor": background_color,
        "font": font,
    }
    if participants:
        payload["participants"] = participants

    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendTextStatus",
        "POST",
        json_body=payload,
    )


def send_voice_status(
    api_url: str,
    instance_id: str,
    api_token: str,
    url_file: str,
    file_name: str,
    background_color: str = "#228B22",
    participants: list[str] = None,
) -> str:
    """Send a voice status.

    Args:
        url_file: URL of the voice file
        file_name: Name of the file
        background_color: Background color in hex format (default: #228B22)
        participants: List of chat IDs who can see the status (optional)
    """
    payload = {
        "urlFile": url_file,
        "fileName": file_name,
        "backgroundColor": background_color,
    }
    if participants:
        payload["participants"] = participants

    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendVoiceStatus",
        "POST",
        json_body=payload,
    )


def send_media_status(
    api_url: str,
    instance_id: str,
    api_token: str,
    url_file: str,
    file_name: str,
    caption: str = "",
    participants: list[str] = None,
) -> str:
    """Send a media (image/video) status.

    Args:
        url_file: URL of the media file
        file_name: Name of the file
        caption: Caption for the media (optional)
        participants: List of chat IDs who can see the status (optional)
    """
    payload = {
        "urlFile": url_file,
        "fileName": file_name,
    }
    if caption:
        payload["caption"] = caption
    if participants:
        payload["participants"] = participants

    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "sendMediaStatus",
        "POST",
        json_body=payload,
    )


def delete_status(api_url: str, instance_id: str, api_token: str, id_message: str) -> str:
    """Delete a status.

    Args:
        id_message: ID of the status message to delete
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "deleteStatus",
        "POST",
        json_body={"idMessage": id_message},
    )


# Receiving API functions


def receive_notification(api_url: str, instance_id: str, api_token: str, receive_timeout: int = 5) -> str:
    """Receive incoming notification from the queue.

    Args:
        receive_timeout: Timeout in seconds for receiving notification (default: 5)
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "receiveNotification",
        "GET",
        query_params={"receiveTimeout": receive_timeout},
    )


def delete_notification(api_url: str, instance_id: str, api_token: str, receipt_id: int) -> str:
    """Delete received notification from the queue.

    Args:
        receipt_id: Receipt ID of the notification to delete
    """
    # Special case: deleteNotification requires receiptId after the token in the URL
    # Format: /waInstance{id}/deleteNotification/{token}/{receiptId}
    url = _build_url(api_url, instance_id, f"deleteNotification/{api_token}/{receipt_id}")
    return send_request("DELETE", url, use_cert=False)


def download_file(api_url: str, instance_id: str, api_token: str, chat_id: str, id_message: str) -> str:
    """Download file from incoming message.

    Args:
        chat_id: Chat ID where the file message was received
        id_message: Message ID of the file message
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "downloadFile",
        "POST",
        json_body={
            "chatId": chat_id,
            "idMessage": id_message,
        },
    )


# Group API functions


def create_group(api_url: str, instance_id: str, api_token: str, group_name: str, chat_ids: list[str]) -> str:
    """Create a new group with specified participants.

    Args:
        group_name: Name for the new group
        chat_ids: List of participant chat IDs (e.g. ["79001234568@c.us", "79001234569@c.us"])
    """
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "createGroup",
        "POST",
        json_body={"groupName": group_name, "chatIds": chat_ids},
    )


def update_group_name(api_url: str, instance_id: str, api_token: str, group_id: str, group_name: str) -> str:
    """Change the name of a group."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "updateGroupName",
        "POST",
        json_body={"groupId": group_id, "groupName": group_name},
    )


def get_group_data(api_url: str, instance_id: str, api_token: str, group_id: str) -> str:
    """Get detailed information about a group."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "getGroupData",
        "POST",
        json_body={"chatId": group_id},
    )


def add_group_participant(
    api_url: str, instance_id: str, api_token: str, group_id: str, participant_chat_id: str
) -> str:
    """Add a participant to a group."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "addGroupParticipant",
        "POST",
        json_body={"chatId": group_id, "participantChatId": participant_chat_id},
    )


def remove_group_participant(
    api_url: str, instance_id: str, api_token: str, group_id: str, participant_chat_id: str
) -> str:
    """Remove a participant from a group."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "removeGroupParticipant",
        "POST",
        json_body={"chatId": group_id, "participantChatId": participant_chat_id},
    )


def set_group_admin(api_url: str, instance_id: str, api_token: str, group_id: str, participant_chat_id: str) -> str:
    """Grant admin rights to a group participant."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "setGroupAdmin",
        "POST",
        json_body={"chatId": group_id, "participantChatId": participant_chat_id},
    )


def remove_group_admin(api_url: str, instance_id: str, api_token: str, group_id: str, participant_chat_id: str) -> str:
    """Remove admin rights from a group participant."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "removeAdmin",
        "POST",
        json_body={"chatId": group_id, "participantChatId": participant_chat_id},
    )


def leave_group(api_url: str, instance_id: str, api_token: str, group_id: str) -> str:
    """Leave a group."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "leaveGroup",
        "POST",
        json_body={"chatId": group_id},
    )


def update_group_settings(
    api_url: str,
    instance_id: str,
    api_token: str,
    group_id: str,
    allow_participants_edit_settings: bool,
    allow_participants_send_messages: bool,
) -> str:
    """Update group settings (who can edit group info and send messages)."""
    return make_api_call(
        api_url,
        instance_id,
        api_token,
        "updateGroupSettings",
        "POST",
        json_body={
            "chatId": group_id,
            "allowParticipantsEditGroupSettings": allow_participants_edit_settings,
            "allowParticipantsSendMessages": allow_participants_send_messages,
        },
    )
