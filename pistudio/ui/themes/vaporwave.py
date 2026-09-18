"""Vaporwave theme — neon pink & teal retro aesthetic."""

from pistudio.ui.theme import Theme, build_logo, register_theme

_LOGO = build_logo(
    ("#ff6ac1", "#ff6ac1", "#ff6ac1", "#ff6ac1", "#2dd4bf", "#2dd4bf"),
    ("#c084fc", "#c084fc", "#7dd3fc", "#7dd3fc", "#2dd4bf", "#2dd4bf"),
)

register_theme(
    Theme(
        name="vaporwave",
        description="🌴  Neon pink & teal — retro aesthetic",
        accent="#ff6ac1",
        secondary="#c084fc",
        success="#2dd4bf",
        error="#fb7185",
        info="#7dd3fc",
        warning="#fbbf24",
        muted="#9488b6",
        text="#e2e8f0",
        border="#8b7fad",
        toolbar_bg="#1e1e2e",
        toolbar_dim="#8c8caa",
        toolbar_text="#a0a0c0",
        prompt_emojis=("🌴", "🥥", "🌺", "🏝️", "🌅", "🦩", "🐬"),
        prompt_color="#ff6ac1",
        prompt_separator="❯",
        prompt_separator_color="#8b7fad",
        logo=_LOGO,
        subtitle_left="░▒▓",
        subtitle_right="▓▒░",
        goodbye_message="🌅 Catch you on the flip side!",
        # Completion colors matching vaporwave palette
        completion_bg="#1e1e2e",  # Dark purple-grey
        completion_bg_selected="#3c3c4c",  # Slightly lighter
        completion_command="#ff6ac1",  # Pink (accent)
        completion_subcommand="#7dd3fc",  # Light blue (info)
        completion_flag="#2dd4bf",  # Teal (success)
        completion_argument="#c084fc",  # Purple (secondary)
        completion_path="#fbbf24",  # Yellow (warning)
        completion_meta="#e2e8f0",  # Light text
        error_voice={
            "not_found": "~* {thing} '{name}' doesn't exist in this reality *~",
            "usage": "Syntax vibes: {usage}",
            "failed": "{action} hit a glitch: {error}",
            "empty_prefix": "Nothing here yet, bestie.",
            "try_instead": "Maybe try: {suggestion}",
            "blocked": "Access denied, aesthetic violation: {reason}",
        },
    )
)
