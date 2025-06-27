from labscript_utils import dedent
from user_devices.logger_config import logger
from qtutils.qt.QtWidgets import QPushButton, QSizePolicy, QHBoxLayout, QSpacerItem, QSizePolicy as QSP

def _get_channel_num(channel: str) -> int:
        """Extracts the channel number from strings like 'AO3', 'ao 3', or 'CH03'.
        Args:
            channel (str): The name of the channel.

        Returns:
            int: Channel number, e.g., 1 to 10.

        Raises:
            ValueError: If the channel string format is invalid or the number is out of range."""
        ch_lower = channel.lower()
        if ch_lower.startswith("ao "):
            channel_num = int(ch_lower[3:]) # 'ao 3' -> 3
        elif ch_lower.startswith("ao"):
            channel_num = int(ch_lower[2:]) # 'ao3' -> 3
        elif ch_lower.startswith("channel"):
            _, channel_num_str = channel.split()  # 'channel 1' -> 1
            channel_num = int(channel_num_str)
        elif ch_lower.startswith("ch "):
            channel_num = int(channel[-2:])  # 'ch 3' -> 3
        elif ch_lower.startswith("ch0"):
            channel_num = int(channel[3:]) # 'ch03' -> 3
        else:
            raise ValueError(f"Unexpected channel name format: '{channel}'")

        return channel_num

def _create_button(text, on_click_callback):
    """Creates a styled QPushButton with consistent appearance and connects it to the given callback."""
    button = QPushButton(text)
    button.setSizePolicy(QSP.Fixed, QSP.Fixed)
    button.adjustSize()
    button.setStyleSheet("""
            QPushButton {
                border: 1px solid #B8B8B8;
                border-radius: 3px;
                background-color: #F0F0F0;
                padding: 4px 10px;
                font-weight: light;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
            }
            QPushButton:pressed {
                background-color: #D0D0D0;
            }
        """)
    button.clicked.connect(lambda: on_click_callback())
    logger.debug(f"Button {text} is created")
    return button