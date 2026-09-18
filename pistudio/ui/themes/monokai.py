"""Monokai theme — warm syntax colors on dark background."""

from pistudio.ui.theme import Theme, build_logo, register_theme

_LOGO = build_logo(
    ("#ff408c", "#ff408c", "#fd971f", "#fd971f", "#e6db74", "#e6db74"),
    ("#a6e22e", "#a6e22e", "#66d9ef", "#66d9ef", "#ae81ff", "#ae81ff"),
)

register_theme(
    Theme(
        name="monokai",
        description="🎨  Monokai Pro — warm syntax on dark",
        accent="#ff408c",
        secondary="#ae81ff",
        success="#a6e22e",
        error="#ff5555",
        info="#66d9ef",
        warning="#fd971f",
        muted="#9b9784",
        text="#f8f8f2",
        border="#75715e",
        toolbar_bg="#272822",
        toolbar_dim="#9b9784",
        toolbar_text="#f8f8f2",
        prompt_emojis=("◈",),
        prompt_color="#ff408c",
        prompt_separator="›",
        prompt_separator_color="#807c69",
        logo=_LOGO,
        subtitle_left="───",
        subtitle_right="───",
        goodbye_message="◈ Signing off. Goodbye!",
        # Completion colors matching Monokai palette
        completion_bg="#272822",  # Dark background
        completion_bg_selected="#43443e",  # Slightly lighter
        completion_command="#ff408c",  # Pink (accent)
        completion_subcommand="#66d9ef",  # Cyan (info)
        completion_flag="#a6e22e",  # Green (success)
        completion_argument="#fd971f",  # Orange (warning)
        completion_path="#ae81ff",  # Purple (secondary)
        completion_meta="#f8f8f2",  # Light text
        error_voice={
            "not_found": "Can't find {thing} '{name}'.",
            "usage": "Usage: {usage}",
            "failed": "Oops, {action} failed: {error}",
            "empty_prefix": "No {thing} yet.",
            "try_instead": "Try: {suggestion}",
            "blocked": "Blocked: {reason}",
        },
    )
)
