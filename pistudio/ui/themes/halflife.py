"""Half-Life theme — orange HEV suit on dark grey, Black Mesa inspired."""

from pistudio.ui.theme import Theme, build_logo, register_theme

_LOGO = build_logo(
    ("#ff6600", "#ff6600", "#ff8533", "#ff8533", "#ffa366", "#ffa366"),
    ("#e65c00", "#e65c00", "#cc5200", "#cc5200", "#b34700", "#b34700"),
)

register_theme(
    Theme(
        name="halflife",
        description="☣️   Half-Life — orange HEV suit on grey",
        accent="#ff6600",
        secondary="#d75d0b",
        success="#ff8533",
        error="#ff3333",
        info="#ffa366",
        warning="#ffcc00",
        muted="#8a8a8a",
        text="#cccccc",
        border="#333333",
        toolbar_bg="#1a1a1a",
        toolbar_dim="#8a8a8a",
        toolbar_text="#999999",
        prompt_emojis=("λ",),
        prompt_color="#ff6600",
        prompt_separator="›",
        prompt_separator_color="#828282",
        logo=_LOGO,
        subtitle_left="───",
        subtitle_right="───",
        goodbye_message="λ Rise and shine, Mr. Freeman. Goodbye!",
        # Completion colors matching Half-Life palette (oranges)
        completion_bg="#1a1a1a",  # Dark grey
        completion_bg_selected="#393939",  # Slightly lighter
        completion_command="#ff6600",  # Orange (accent)
        completion_subcommand="#ffa366",  # Light orange (info)
        completion_flag="#ffcc00",  # Yellow (warning)
        completion_argument="#ff8533",  # Orange (success)
        completion_path="#cc5200",  # Dark orange (secondary)
        completion_meta="#cccccc",  # Grey text
        error_voice={
            "not_found": "WARNING: {thing} '{name}' not found in system.",
            "usage": "USAGE: {usage}",
            "failed": "CRITICAL: {action} failed — {error}",
            "empty_prefix": "No {thing} detected.",
            "try_instead": "Recommendation: {suggestion}",
            "blocked": "ACCESS DENIED: {reason}",
        },
    )
)
