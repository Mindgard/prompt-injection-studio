"""Studio theme — teal, indigo & dark navy."""

from pistudio.ui.theme import Theme, build_logo, register_theme

_LOGO = build_logo(
    ("#00e5c8", "#00e5c8", "#00d4b8", "#00d4b8", "#34d399", "#34d399"),
    ("#6366f1", "#6366f1", "#818cf8", "#818cf8", "#a5b4fc", "#a5b4fc"),
)

register_theme(
    Theme(
        name="studio",
        description="🎯  Studio — teal, indigo & navy",
        accent="#00e5c8",
        secondary="#818cf8",
        success="#34d399",
        error="#f87171",
        info="#67e8f9",
        warning="#fbbf24",
        muted="#74849b",
        text="#e2e8f0",
        border="#334155",
        toolbar_bg="#0a0e1a",
        toolbar_dim="#74849b",
        toolbar_text="#94a3b8",
        prompt_emojis=("🛡️",),
        prompt_color="#00e5c8",
        prompt_separator="❯",
        prompt_separator_color="#74849b",
        logo=_LOGO,
        subtitle_left="───",
        subtitle_right="───",
        goodbye_message="🎯 Stay sharp. Goodbye!",
        # Completion colors matching the studio palette
        completion_bg="#0a0e1a",  # Dark navy
        completion_bg_selected="#2e323e",  # Slightly lighter
        completion_command="#00e5c8",  # Teal (accent)
        completion_subcommand="#67e8f9",  # Light cyan (info)
        completion_flag="#34d399",  # Green (success)
        completion_argument="#fbbf24",  # Yellow (warning)
        completion_path="#818cf8",  # Indigo (secondary)
        completion_meta="#e2e8f0",  # Light text
        error_voice={
            "not_found": "{thing} '{name}' not found.",
            "usage": "Usage: {usage}",
            "failed": "Could not {action}: {error}",
            "empty_prefix": "No {thing} yet.",
            "try_instead": "Try: {suggestion}",
            "blocked": "Blocked by policy: {reason}",
        },
    )
)
