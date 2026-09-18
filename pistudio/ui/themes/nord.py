"""Nord theme — arctic, calm blues and greens."""

from pistudio.ui.theme import Theme, build_logo, register_theme

_LOGO = build_logo(
    ("#88c0d0", "#88c0d0", "#5e81ac", "#5e81ac", "#a3be8c", "#a3be8c"),
    ("#81a1c1", "#81a1c1", "#b48ead", "#b48ead", "#a3be8c", "#a3be8c"),
)

register_theme(
    Theme(
        name="nord",
        description="❄️   Nord — arctic, calm blues & greens",
        accent="#88c0d0",
        secondary="#81a1c1",
        success="#a3be8c",
        error="#ee7a6a",
        info="#88c0d0",
        warning="#ebcb8b",
        muted="#9ba5b9",
        text="#d8dee9",
        border="#4c566a",
        toolbar_bg="#2e3440",
        toolbar_dim="#9ba5b9",
        toolbar_text="#d8dee9",
        prompt_emojis=("❄",),
        prompt_color="#88c0d0",
        prompt_separator="›",
        prompt_separator_color="#737d91",
        logo=_LOGO,
        subtitle_left="───",
        subtitle_right="───",
        goodbye_message="❄ Stay frosty. Goodbye!",
        # Completion colors matching Nord palette
        completion_bg="#2e3440",  # Polar Night
        completion_bg_selected="#494f5b",  # Slightly lighter
        completion_command="#88c0d0",  # Frost cyan (accent)
        completion_subcommand="#81a1c1",  # Frost blue (secondary)
        completion_flag="#a3be8c",  # Aurora green (success)
        completion_argument="#ebcb8b",  # Aurora yellow (warning)
        completion_path="#b48ead",  # Aurora purple
        completion_meta="#d8dee9",  # Snow Storm (text)
        error_voice={
            "not_found": "{thing} '{name}' was not found.",
            "usage": "Usage: {usage}",
            "failed": "Unable to {action}. {error}",
            "empty_prefix": "No {thing} found.",
            "try_instead": "Suggestion: {suggestion}",
            "blocked": "Operation blocked. {reason}",
        },
    )
)
