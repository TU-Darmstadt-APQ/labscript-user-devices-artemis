from labscript_utils import dedent

def _get_channel_num(channel: str) -> int:
        """Gets channel number from strings like 'AOX' or 'channel X'.
        Args:
            channel (str): The name of the channel, e.g. 'AO0', 'AO12', or 'channel 3'.

        Returns:
            int: e.g. 1..8 """
        ch_lower = channel.lower()
        if ch_lower.startswith("ao"):
            channel_num = int(channel[2:])  # 'ao0' -> '1'
        elif ch_lower.startswith("ch "):
            channel_num = int(channel[-2:])   # 'ao0' -> '1'
        elif ch_lower.startswith("channel"):
            _, channel_num_str = channel.split()  # 'channel 1' -> '1'
            channel_num = int(channel_num_str)
        else:
            msg = """Unexpected channel name format: """
            raise ValueError(dedent(msg) % str(channel))

        return channel_num