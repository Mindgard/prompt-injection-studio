"""Borland theme — classic Borland IDE blue background, yellow & white."""

from pistudio.ui.theme import Theme, build_logo, register_theme

_LOGO = build_logo(
    ("bold #ffff54",),
    ("bold #ffff54",),
)

register_theme(
    Theme(
        name="borland",
        description="💾  Borland IDE — blue, yellow & white",
        accent="#ffff54",
        secondary="#55ffff",
        success="#55ff55",
        error="#ff6666",
        info="#55ffff",
        warning="#ffff54",
        muted="#aaaaaa",
        text="#ffffff",
        border="#55ffff",
        toolbar_bg="#0000aa",
        toolbar_dim="#aaaaaa",
        toolbar_text="#ffffff",
        prompt_emojis=("▸",),
        prompt_color="#ffff54",
        prompt_separator=">",
        prompt_separator_color="#55ffff",
        logo=_LOGO,
        subtitle_left="═══",
        subtitle_right="═══",
        goodbye_message="▸ End of session. Goodbye!",
        # Completion colors matching Borland palette
        completion_bg="#000066",  # Darker Borland blue
        completion_bg_selected="#29298f",  # Lighter for selection highlight
        completion_command="#ffff54",  # Yellow (accent)
        completion_subcommand="#55ffff",  # Cyan (secondary)
        completion_flag="#55ff55",  # Green (success)
        completion_argument="#ffffff",  # White (text)
        completion_path="#55ffff",  # Cyan (info)
        completion_meta="#aaaaaa",  # Grey (muted)
        error_voice={
            "not_found": "Error: {thing} '{name}' not found in registry.",
            "usage": "Syntax: {usage}",
            "failed": "Runtime error in {action}: {error}",
            "empty_prefix": "No {thing} defined.",
            "try_instead": "Hint: {suggestion}",
            "blocked": "Access violation: {reason}",
        },
    )
)
