# TemporalTextSummarization
The code for construct US subcommittee meeting transcript.
datadownload will download the audio to audio_full folder, and meeting detail to output folder
extract will run segmentation, pyannote and whisper, then store the results to output folder

# Create folder 
audio_segment, audio_full, pdf, output

# Change city name in the two codes file when needed

# Package install
pip3 uninstall torch torchvision torchaudio
pip3 cache purge
pip install cuda-python
pip3 install torch torchvision torchaudio
pip3 install -U openai-whisper
pip3 install pymupdf bs4 pdfminer.six soundfile pydub
pip3 install pyannote.audio
pip3 install pdfminer.six

# Run datadownload
nohup python download_data.py > output.log 2>&1 &

# Run extract
nohup python extract_longbeach_GPU.py > output_extract4.log 2>&1 &
