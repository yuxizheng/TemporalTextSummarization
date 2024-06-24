import torch
import requests
from bs4 import BeautifulSoup
import re
from pdfminer.high_level import extract_text
import json
from pydub import AudioSegment
import whisper
import fitz
import os
from pyannote.audio import Pipeline
import whisper
import json
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import time


def get_aac(url):
    response = requests.get(url)
    response.raise_for_status()  # This will raise an exception for HTTP errors

    # Define a regular expression pattern to find the URLs
    pattern = r'video_url="https://archive-stream.granicus.com/OnDemand/[^"]+"'

    # Search for all occurrences of the pattern
    matches = re.findall(pattern, response.text)

    for match in matches:
        # Extract just the URL part from the whole match
        url_match = match.split('"')[1]  # Split by quotes and get the second element
    
    file_name_regex = re.search(r'longbeach_(.+)\.mp4', url_match)
    if file_name_regex:
        unique_name = file_name_regex.group(1)
        output_file_path = os.path.join('./audio_full', f'longbeach_{unique_name}.aac')
    else:
        print("Error: Could not extract file name from URL.")
        exit(1)  # Exit if no match is found
    
    if os.path.exists(output_file_path):
        print(f"File already exists: {output_file_path}")
        return output_file_path 
    else: 
        return None

def segment_audio(audio_path, start_ms, end_ms, segment_path):
    if start_ms and end_ms:
        try:
            audio = AudioSegment.from_file(audio_path)
            segment = audio[start_ms:end_ms]
            segment.export(segment_path, format="wav")
        except FileNotFoundError:
            print(f"Segment Audio: File not exists: {audio_path}")
    return 
        
    
def transcribe_segment(audio_path, start_time, end_time):
    # This function extracts and transcribes segments using the provided model.
    # Ensure that the model is loaded on the GPU for faster processing.
    # Load the audio segment
    if start_time and end_time:
        segment_audio = AudioSegment.from_wav(audio_path)[start_time * 1000:end_time * 1000]
        segment_audio.export("temp_segment.wav", format="wav")

        # Transcribe the temporary segment file
        with torch.no_grad():
            result = model.transcribe("temp_segment.wav")

        return result['text']
    else:
        return ' '

def diarization_and_transcription(audio_path):
    # Perform diarization
    diarization = pipeline(audio_path)
    transcript = ""
    
    for segment, _, speaker in diarization.itertracks(yield_label=True):
        start, end = segment.start, segment.end
        transcription = transcribe_segment(audio_path, start, end)
        # Append each transcription to the transcript string, adding the speaker label and a newline
        if transcription != "":
            transcript += f"{speaker}: {transcription} \n"
    return transcript.strip()


def get_itemInfo_from_file(filepath):
    with open(filepath, 'r') as file:
        data = json.load(file)
    return data

def process_line(line, output_dir, file_extension, model, pipeline):
    url = line.strip()
    print("now transcribing: ", url, flush=True)
    filename = url.replace('https://', '').replace('/', '_').replace('?', '_').replace(':', '_').replace('&', '_')
    filepath = os.path.join(output_dir, f"{filename}.{file_extension}")
    itemInfo = get_itemInfo_from_file(filepath)

    for pattern in itemInfo:
        print("Transcribing pattern: ", pattern)
        start_time = itemInfo[pattern].get('startTime')
        end_time = itemInfo[pattern].get('endTime')
        if start_time is not None and end_time is not None:
            segment_path = os.path.join('./audio_segment', f"segment_{pattern}.wav")
            print("Segment_path: ", segment_path)
            diarization = pipeline(segment_path)
            print("Diarization end for:", segment_path)

            transcript = ""
            for segment, _, speaker in diarization.itertracks(yield_label=True):
                start, end = segment.start, segment.end
                if start and end:
                    segment_audio = AudioSegment.from_wav(segment_path)[start * 1000:end * 1000]
                    segment_audio.export("temp_segment.wav", format="wav")

                    # Transcribe the temporary segment file
                    with torch.no_grad():
                        result = model.transcribe("temp_segment.wav")

                    single_transcript = result['text']
                else:
                    single_transcript = ' '
                # Append each transcription to the transcript string, adding the speaker label and a newline
                if single_transcript != "":
                    transcript += f"{speaker}: {single_transcript} \n"

            transcript = transcript.strip()
            itemInfo[pattern]['transcript'] = transcript
            print("done transcript for: ", segment_path, flush=True)

    file_path = os.path.join(output_dir, filename)
    with open(file_path + '.json', 'w') as f:
        json.dump(itemInfo, f, indent=4)
    return url

if __name__ == "__main__":
    torch.cuda.init()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # add pyannote token here
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token="YOUR_TOKEN")
    pipeline = pipeline.to(device)
    model = whisper.load_model("base", device=device)
    output_dir = './output_longbeach'
    file_extension = "json"
    
    with open('meeting_list/longbeach2.txt', 'r') as file:
        lines = file.readlines()
        
    timeout_limit = 600
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(process_line, line, output_dir, file_extension, model, pipeline): line for line in lines}

    while futures:
        for future in futures.copy():
            try:
                # Calculate the remaining time for this future
                elapsed_time = time.time() - start_time
                remaining_time = timeout_limit - elapsed_time

                if remaining_time <= 0:
                    print("Total processing time exceeded 10 minutes. Ending process.", flush=True)
                    futures.clear()  # Clear all remaining futures to break out of the while loop
                    break

                # Use the remaining time as the timeout for each future
                url = future.result(timeout=remaining_time)
                print(f"Completed transcription for: {url}", flush=True)
                
                # Remove the completed future from the dictionary
                futures.pop(future)
                
            except TimeoutError:
                print(f"Transcription for {futures[future]} took too long and was skipped.", flush=True)
                futures.pop(future)
            except Exception as e:
                print(f"An error occurred: {e}", flush=True)
                futures.pop(future)
        