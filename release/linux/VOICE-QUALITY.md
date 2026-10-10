# Spoken phonetics on Linux

CallPerch's **Speak phonetics** button uses the installed eSpeak NG (or eSpeak) English voice. It works locally and is lightweight, but can sound noticeably synthetic. It is a listening aid, not a pronunciation standard.

## Try a more natural voice separately

[Piper](https://github.com/OHF-Voice/piper1-gpl) is an optional local neural speech tool. Listen to its [voice samples](https://rhasspy.github.io/piper-samples/) before choosing a voice. Installation and voice downloads need an internet connection; subsequent speech generation runs locally.

The following example uses a separate environment, without changing CallPerch's dependencies:

```sh
mkdir -p "$HOME/.local/share/callperch-voice-demo"
cd "$HOME/.local/share/callperch-voice-demo"
python3 -m venv .venv
.venv/bin/python -m pip install piper-tts
.venv/bin/python -m piper.download_voices en_US-lessac-medium
.venv/bin/python -m piper -m en_US-lessac-medium -f phonetics.wav -- 'Kilo Eight Zulu Tango'
```

Open `phonetics.wav` in your audio player. Replace the example sentence with the phonetic words displayed in your CallPerch comparison. Other voices can be downloaded using the same procedure. See [Piper's official instructions](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md) for supported installations and options.

**This is a separate listening option. Downloading a Piper voice does not change CallPerch's Speak phonetics button.** The current Linux app has no Piper integration or voice selector. Piper and its voices are not bundled with CallPerch. Voice models have their own license terms; check the selected model's documentation. Listen to the generated words, since natural-sounding speech can still pronounce phonetics differently than intended.
