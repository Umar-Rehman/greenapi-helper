"""Tab configuration data for the main application."""

# Tab configuration structure: Each tab has sections, each section has buttons
TAB_CONFIG = {
    "Account": {
        "sections": [
            {
                "title": "Instance Information",
                "buttons": [
                    {
                        "text": "Get Instance Information (API Token / URL)",
                        "handler": "run_get_api_token",
                    },
                    {"text": "Get Instance State", "handler": "run_get_instance_state"},
                    {"text": "Get Instance Settings", "handler": "run_get_instance_settings"},
                    {"text": "Get Account Settings", "handler": "run_get_account_settings"},
                ],
            },
            {
                "title": "Authentication",
                "buttons": [
                    {"text": "Get QR Code", "handler": "run_get_qr_code"},
                    {"text": "Get Authorization Code", "handler": "run_get_authorization_code"},
                ],
            },
            {
                "title": "Telegram Authentication",
                "buttons": [
                    {
                        "text": "Start Phone Authorization",
                        "handler": "run_start_authorization",
                        "action_type": "post",
                    },
                    {
                        "text": "Send Authorization Code",
                        "handler": "run_send_authorization_code",
                        "action_type": "post",
                    },
                    {
                        "text": "Send 2FA Password",
                        "handler": "run_send_authorization_password",
                        "action_type": "post",
                    },
                ],
            },
            {
                "title": "Profile",
                "buttons": [
                    {
                        "text": "Set Profile Picture",
                        "handler": "run_set_profile_picture",
                        "action_type": "post",
                    },
                ],
            },
            {
                "title": "Configuration",
                "buttons": [
                    {
                        "text": "Set Instance Settings",
                        "handler": "run_set_instance_settings",
                        "action_type": "post",
                    },
                    {
                        "text": "Update API Token",
                        "handler": "run_update_api_token",
                        "action_type": "danger",
                    },
                ],
            },
            {
                "title": "Dangerous Actions",
                "buttons": [
                    {"text": "Logout Instance", "handler": "run_logout_instance", "action_type": "danger"},
                    {"text": "Reboot Instance", "handler": "run_reboot_instance", "action_type": "danger"},
                ],
            },
        ],
    },
    "Journals": {
        "sections": [
            {
                "title": "Message History",
                "buttons": [
                    {
                        "text": "Get Incoming Messages Journal",
                        "handler": "run_get_incoming_msgs_journal",
                    },
                    {
                        "text": "Get Outgoing Messages Journal",
                        "handler": "run_get_outgoing_msgs_journal",
                    },
                    {"text": "Get Chat History", "handler": "run_get_chat_history", "action_type": "post"},
                    {"text": "Get Message", "handler": "run_get_message", "action_type": "post"},
                ],
            },
        ],
    },
    "Queues": {
        "sections": [
            {
                "title": "Message Queues",
                "buttons": [
                    {
                        "text": "Get Message Queue Count",
                        "handler": "run_get_msg_queue_count",
                    },
                    {
                        "text": "Show Messages Queue",
                        "handler": "run_get_msg_queue",
                    },
                    {
                        "text": "Clear Messages Queue",
                        "handler": "run_clear_msg_queue",
                        "action_type": "post",
                    },
                ],
            },
            {
                "title": "File Queues",
                "buttons": [
                    {
                        "text": "Show Files Queue",
                        "handler": "run_get_webhook_count",
                    },
                    {
                        "text": "Clear Files Queue",
                        "handler": "run_clear_webhooks",
                        "action_type": "danger",
                    },
                ],
            },
        ],
    },
    "Groups": {
        "sections": [
            {
                "title": "Group Management",
                "buttons": [
                    {"text": "Create Group", "handler": "run_create_group", "action_type": "post"},
                    {"text": "Update Group Name", "handler": "run_update_group_name", "action_type": "post"},
                    {"text": "Get Group Data", "handler": "run_get_group_data", "action_type": "post"},
                    {
                        "text": "Add Group Participant",
                        "handler": "run_add_group_participant",
                        "action_type": "post",
                    },
                    {
                        "text": "Remove Group Participant",
                        "handler": "run_remove_group_participant",
                        "action_type": "post",
                    },
                    {
                        "text": "Set Group Admin",
                        "handler": "run_set_group_admin",
                        "action_type": "post",
                    },
                    {
                        "text": "Remove Group Admin",
                        "handler": "run_remove_group_admin",
                        "action_type": "post",
                    },
                    {
                        "text": "Update Group Settings",
                        "handler": "run_update_group_settings",
                        "action_type": "post",
                    },
                    {"text": "Leave Group", "handler": "run_leave_group", "action_type": "danger"},
                ],
            },
        ],
    },
    "Sending": {
        "sections": [
            {
                "title": "Send Messages",
                "buttons": [
                    {"text": "Send Text Message", "handler": "run_send_message", "action_type": "post"},
                    {"text": "Send File by URL", "handler": "run_send_file_by_url", "action_type": "post"},
                    {"text": "Send Location", "handler": "run_send_location", "action_type": "post"},
                    {"text": "Send Contact", "handler": "run_send_contact", "action_type": "post"},
                    {"text": "Send Poll", "handler": "run_send_poll", "action_type": "post"},
                ],
            },
            {
                "title": "Forwarding",
                "buttons": [
                    {"text": "Forward Messages", "handler": "run_forward_messages", "action_type": "post"},
                ],
            },
        ],
    },
    "Receiving": {
        "sections": [
            {
                "title": "Webhooks",
                "buttons": [
                    {"text": "Receive Notification", "handler": "run_receive_notification"},
                    {"text": "Delete Notification", "handler": "run_delete_notification", "action_type": "danger"},
                ],
            },
            {
                "title": "Files",
                "buttons": [
                    {"text": "Download File", "handler": "run_download_file", "action_type": "post"},
                ],
            },
        ],
    },
    "Statuses": {
        "sections": [
            {
                "title": "Message Statuses",
                "buttons": [
                    {"text": "Get Incoming Statuses", "handler": "run_get_incoming_statuses"},
                    {"text": "Get Outgoing Statuses", "handler": "run_get_outgoing_statuses"},
                    {"text": "Get Status Statistic", "handler": "run_get_status_statistic"},
                ],
            },
            {
                "title": "WhatsApp Statuses",
                "buttons": [
                    {"text": "Send Text Status", "handler": "run_send_text_status", "action_type": "post"},
                    {"text": "Send Voice Status", "handler": "run_send_voice_status", "action_type": "post"},
                    {"text": "Send Media Status", "handler": "run_send_media_status", "action_type": "post"},
                    {"text": "Delete Status", "handler": "run_delete_status", "action_type": "danger"},
                ],
            },
        ],
    },
    "Service Methods": {
        "sections": [
            {
                "title": "Phone Utilities",
                "buttons": [
                    {
                        "text": "Check WhatsApp Account",
                        "handler": "run_check_whatsapp",
                        "action_type": "post",
                    },
                    {
                        "text": "Check MAX Availability",
                        "handler": "run_check_max",
                        "action_type": "post",
                    },
                    {"text": "Get Contacts", "handler": "run_get_contacts"},
                    {"text": "Get Contact Info", "handler": "run_get_contact_info", "action_type": "post"},
                    {
                        "text": "Get Avatar (Profile Picture)",
                        "handler": "run_get_avatar",
                        "action_type": "post",
                    },
                ],
            },
            {
                "title": "Message Operations",
                "buttons": [
                    {"text": "Edit Message", "handler": "run_edit_message", "action_type": "post"},
                    {"text": "Delete Message", "handler": "run_delete_message", "action_type": "danger"},
                ],
            },
            {
                "title": "Chat Operations",
                "buttons": [
                    {"text": "Archive Chat", "handler": "run_archive_chat", "action_type": "post"},
                    {"text": "Unarchive Chat", "handler": "run_unarchive_chat", "action_type": "post"},
                    {"text": "Set Disappearing Chat", "handler": "run_set_disappearing_chat", "action_type": "post"},
                ],
            },
        ],
    },
    "Read Mark": {
        "sections": [
            {
                "title": "Message Marking",
                "buttons": [
                    {"text": "Mark Message as Read", "handler": "run_mark_message_as_read", "action_type": "post"},
                    {"text": "Mark Chat as Read", "handler": "run_mark_chat_as_read", "action_type": "post"},
                ],
            },
        ],
    },
}
