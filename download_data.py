import torch
import requests
from bs4 import BeautifulSoup
import re
import subprocess
from pdfminer.high_level import extract_text
import json
from pydub import AudioSegment
import whisper
import fitz
import os
from pyannote.audio import Pipeline
import whisper
from pydub import AudioSegment
import json

def download_aac(url):
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
    
    command = [
        'ffmpeg', 
        '-i', url_match,  # Use the dynamic URL
        '-vn', 
        '-acodec', 'copy', 
        output_file_path  # Use the dynamic file name
    ]

    # Execute the command
    subprocess.run(command)
    return output_file_path

# Function to download a PDF file from a given URL
def download_pdf(url):
    def get_pdf(pdf_url, file_name):
        response = requests.get(pdf_url)
        if response.status_code == 200:
            with open(file_name, 'wb') as f:
                f.write(response.content)
            print(f"PDF downloaded successfully: {file_name}")
        else:
            print(f"Failed to download the PDF. Status code: {response.status_code}")

    # Send a GET request to fetch the webpage content
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML content of the page
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the first element with a 'data-url' attribute ending with '.pdf'
        pdf_link_tag = soup.find(attrs={"data-url": lambda x: x and x.endswith('.pdf')})
        
        if pdf_link_tag:
            pdf_link = pdf_link_tag['data-url']
            print(f"PDF Link found: {pdf_link}")
            # Define a file name for the downloaded PDF
            file_path = os.path.join('./pdf', pdf_link.split('/')[-1])
            
            if os.path.exists(file_path):
                print(f"File already exists: {file_path}")
                return file_path 
            # Download the PDF
            get_pdf(pdf_link, file_path)
            
            return file_path
        else:
            print("No PDF links found.")
    else:
        print("Failed to fetch the webpage.")

def extract_text(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

def get_text_itemInfo_from_pdf(pdf_file):
    doc = fitz.open(pdf_file)
    links_info = []
    itemInfo = {}

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        links = page.get_links()

        for link in links:
            link_rect = link.get('from')
            linked_text = page.get_text("text", clip=link_rect)
            linked_text = linked_text.split('\n')[0].split('\t')[0].strip()
            if linked_text:  # Ensure linked_text is not empty
                links_info.append(linked_text)

    doc.close()

    text = extract_text(pdf_file)
    clean_text = text  # No need to replace '\n' here as we're going to remove them

    # Iterate through links_info in pairs
    for i in range(len(links_info) - 1):
        start_text = links_info[i]
        end_text = links_info[i + 1]
        pattern = re.escape(start_text) + r"([\s\S]*?)" + re.escape(end_text)
        match = re.search(pattern, clean_text)

        if match:
            summary = match.group(1).strip()
            # Remove all newline characters from the summary
            summary = summary.replace('\n', '').strip()
            itemInfo[start_text] = {"summary": summary}

    # Optional: Handle the last link's summary here if needed
    return itemInfo

def get_time_itemInfo_from_url(url, itemInfo):
    response = requests.get(url)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Iterate through each match to find corresponding divs for startTime and endTime
        for pattern in itemInfo:
            for div in soup.find_all("div", class_="index-point flex-col-center"):
                if pattern in div.text:
                    itemInfo[pattern]["startTime"] = div.get("time")
                    # Find the next div with a time attribute to set as endTime
                    next_div = div.find_next_sibling("div", class_="index-point flex-col-center")
                    if next_div:
                        itemInfo[pattern]["endTime"] = next_div.get("time")
                    else:
                        itemInfo[pattern]["endTime"] = "Unknown"
                    break  # Exit the loop once the relevant divs are found

    else:
        print("Failed to fetch the webpage.")
        
    return itemInfo


def segment_audio(audio_path, start_ms, end_ms, segment_path):
    audio = AudioSegment.from_file(audio_path)
    segment = audio[start_ms:end_ms]
    segment.export(segment_path, format="wav")

def get_itemInfo_from_file(filepath):
    with open(filepath, 'r') as file:
        data = json.load(file)
    return data

def delete_audio_file(file_path):
    try:
        os.remove(file_path)
        print(f"File '{file_path}' deleted successfully.")
    except FileNotFoundError:
        print(f"Delete: File not exists: {file_path}")

def cut_aac(itemInfo, audio_path):
    for pattern in itemInfo:
        start_time = itemInfo[pattern].get('startTime')
        end_time = itemInfo[pattern].get('endTime')
        if start_time is not None and end_time is not None:
            start_ms = int(start_time) * 1000 if start_time != 'Unknown' else None # Convert seconds to milliseconds
            end_ms = int(end_time) * 1000 if end_time != 'Unknown' else None
            segment_path = os.path.join('./audio_segment', f"segment_{pattern}.wav")
            if not os.path.exists(segment_path):
                segment_audio(audio_path, start_ms, end_ms, segment_path)
            print(pattern)

if __name__ == "__main__":
    # output_dir = './output_longbeach'
    # if not os.path.exists(output_dir):
    #     os.makedirs(output_dir)
        
    # with open('meeting_list/longbeach.txt', 'r') as file:
    #     for line in file:
            
    #         url = line.strip()
    #         filename = url.replace('https://', '').replace('/', '_').replace('?', '_').replace(':', '_').replace('&', '_')
    #         file_path = os.path.join(output_dir, filename)
            
    #             audio_path = download_aac(url)
    #             pdf_file = download_pdf(url)
    #             itemInfo = get_text_itemInfo_from_pdf(pdf_file)
    #             itemInfo = get_time_itemInfo_from_url(url, itemInfo)

    #         with open(file_path + '.json', 'w') as f:
    #             json.dump(itemInfo, f, indent=4)

    output_dir = './output_longbeach'
    file_extension = "json"

    with open('meeting_list/longbeach.txt', 'r') as file:
        for line in file:
            
            url = line.strip()
            filename = url.replace('https://', '').replace('/', '_').replace('?', '_').replace(':', '_').replace('&', '_')
            filepath = os.path.join(output_dir, f"{filename}.{file_extension}")
            
            if os.path.exists(filepath):
                continue
            
            audio_path = download_aac(url)
            
            pdf_file = download_pdf(url)
            itemInfo = get_text_itemInfo_from_pdf(pdf_file)
            itemInfo = get_time_itemInfo_from_url(url, itemInfo)
            cut_aac(itemInfo, audio_path)

            with open(filepath, 'w') as f:
                json.dump(itemInfo, f, indent=4)