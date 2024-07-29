import json
import hashlib
import requests
from requests.exceptions import RequestException
import sqlite3
import html2text
from bs4 import BeautifulSoup
import sys
import os
import glob
import urllib.parse

# Utility function to calculate md5 hash using href and toc_title
def md5_hash(href, toc_title):    # Treat href as an empty string if it's None
    if href is None:
        href = ""
    combined_str = f"{href}_{toc_title}"
    return hashlib.md5(combined_str.encode()).hexdigest()

# Recursive function to process JSON and insert into database
def process_json(items, base_url, parent_id=None):
    for item in items:
        item_id = None
        href = item.get('href', None)
        toc_title = item.get('toc_title', 'No title')

        item_id = md5_hash(href, toc_title)
        with sqlite3.connect('docs.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO documentation (id, parent_id, toc_title, href)
                VALUES (?, ?, ?, ?)
            ''', (item_id, parent_id, toc_title, href))
            conn.commit()
                
        if 'children' in item:
            process_json(item['children'], base_url, item_id if item_id else parent_id)

# Function to download HTML content and extract specific div with class attribute "content"
def download_content(item, base_url, index, total_count):
    item_id, href = item

    if not href:
        return

    # Construct the full URL using urllib.parse.urljoin for reliability
    full_url = urllib.parse.urljoin(base_url, href)
    try:
        response = requests.get(full_url)
        response.raise_for_status()  # Raise exception for HTTP errors
        html_content = response.text

        # Extract content from div with class "content"
        soup = BeautifulSoup(html_content, 'html.parser')
        content_div = soup.find('div', class_='content')

        if content_div:
            extracted_html = str(content_div)
            markdown_content = html2text.html2text(extracted_html)
        else:
            extracted_html = None
            markdown_content = None

        with sqlite3.connect('docs.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE documentation
                SET html_content = ?, markdown_content = ?
                WHERE id = ?
            ''', (extracted_html, markdown_content, item_id))
            conn.commit()

        # Save markdown content to file in the markdown folder
        save_markdown_file(item_id, markdown_content)

        # Print progress
        sys.stdout.write(f"\rProcessing {index + 1} out of {total_count}\n")
        sys.stdout.write(f"Title: {soup.title.string if soup.title else 'No title'}\n")
        sys.stdout.write(f"URL: {full_url}\n")
        sys.stdout.flush()

    except RequestException as e:
        sys.stdout.write(f"\rFailed to download {full_url}: {e}\n")
        sys.stdout.flush()

def save_markdown_file(item_id, markdown_content):
    if markdown_content:
        # Create markdown directory if it doesn't exist
        markdown_dir = 'markdown'
        os.makedirs(markdown_dir, exist_ok=True)

        # Save the markdown content to a file named 'md5id.md'
        markdown_file_path = os.path.join(markdown_dir, f"{item_id}.md")
        with open(markdown_file_path, 'w', encoding='utf-8') as markdown_file:
            markdown_file.write(markdown_content)
        print(f"Markdown content saved to {markdown_file_path}")
    else:
        print(f"No markdown content to save for ID: {item_id}")

def process_file(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        base_url = data.get('baseUrl')
        if not base_url:
            print(f"Skipping {filepath} as it does not contain a baseUrl key.")
            return

        items = data.get('data', {}).get('items', None)
        if not items:
            print(f"Skipping {filepath} as it does not contain an 'items' key.")
            return

        # Process JSON and insert data into the database
        process_json(items, base_url)

        # Get a list of items without HTML content for processing
        with sqlite3.connect('docs.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, href FROM documentation WHERE html_content IS NULL AND href IS NOT NULL
            ''')
            items_to_process = cursor.fetchall()

        total_count = len(items_to_process)

        # Process each item sequentially
        for index, item in enumerate(items_to_process):
            download_content(item, base_url, index, total_count)
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from file {filepath}. Skipping.")
    except Exception as e:
        print(f"An error occurred while processing file {filepath}: {e}")

def main():
    # Fetch all JSON files in the 'sources' directory
    json_files = glob.glob(os.path.join('sources', '*.json'))

    if not json_files:
        print("No JSON files found in the sources directory.")
        return

    # Ensure the output database exists
    if not os.path.exists('docs.db'):
        with sqlite3.connect('docs.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documentation (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    toc_title TEXT,
                    href TEXT,
                    html_content TEXT,
                    markdown_content TEXT,
                    FOREIGN KEY (parent_id) REFERENCES documentation (id)
                )
            ''')
            conn.commit()

    # Process each JSON file
    for filepath in json_files:
        print(f"Processing file: {filepath}")
        process_file(filepath)

if __name__ == '__main__':
    main()