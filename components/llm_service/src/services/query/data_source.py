# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Query Data Sources
"""
import os
from copy import copy
from base64 import b64encode
from typing import List, Tuple
from pathlib import Path
from common.utils.logging_handler import Logger
from langchain.text_splitter import CharacterTextSplitter
from langchain.document_loaders import CSVLoader
from pypdf import PdfReader, PdfWriter, PageObject
from utils.errors import NoDocumentsIndexedException
from utils import text_helper

# pylint: disable=broad-exception-caught

# text chunk size for embedding data
Logger = Logger.get_logger(__file__)
CHUNK_SIZE = 1000


class DataSource:
  """
  Class for query data sources
  """

  def __init__(self, storage_client):
    self.storage_client = storage_client
    self.docs_not_processed = []

  def download_documents(self, doc_url: str, temp_dir: str) -> \
        List[Tuple[str, str, str]]:
    """
    Download files from doc_url source to a local tmp directory

    Args:
        doc_url: url pointing to container of documents to be indexed
        temp_dir: Path to temporary directory to download files to

    Returns:
        list of tuples (doc name, document url, local file path)
    """
    doc_filepaths = []
    bucket_name = doc_url.split("gs://")[1].split("/")[0]
    Logger.info(f"downloading {doc_url} from bucket {bucket_name}")

    for blob in self.storage_client.list_blobs(bucket_name):
      # Download the file to the tmp folder flattening all directories
      file_name = Path(blob.name).name
      file_path = os.path.join(temp_dir, file_name)
      blob.download_to_filename(file_path)
      doc_filepaths.append((blob.name, blob.path, file_path))

    if len(doc_filepaths) == 0:
      raise NoDocumentsIndexedException(
          f"No documents can be indexed at url {doc_url}")

    return doc_filepaths

  def chunk_document(self, doc_name: str, doc_url: str,
                     doc_filepath: str) -> List[str]:
    """
    Process doc into chunks for embeddings

    Args:
       doc_name: file name of document
       doc_url: remote url of document
       doc_filepath: local file path of document
    Returns:
       list of text chunks or None if the document could not be processed
    """

    text_chunks = None

    # use langchain text splitter
    text_splitter = CharacterTextSplitter(chunk_size=CHUNK_SIZE,
                                          chunk_overlap=0)

    Logger.info(f"generating index data for {doc_name}")

    # read doc data and split into text chunks
    # skip any file that can't be read or generates an error
    doc_text_list = None
    try:
      doc_text_list = self.read_doc(doc_name, doc_filepath)
      if doc_text_list is None:
        Logger.error(f"no content read from {doc_name}")
        self.docs_not_processed.append(doc_url)
    except Exception as e:
      Logger.error(f"error reading doc {doc_name}: {e}")
      self.docs_not_processed.append(doc_url)

    if doc_text_list is not None:
      # split text into chunks
      text_chunks = []
      for text in doc_text_list:
        text_chunks.extend(text_splitter.split_text(text))

      if all(element == "" for element in text_chunks):
        Logger.warning(f"All extracted pages from {doc_name} are empty.")
        self.docs_not_processed.append(doc_url)

      # clean up text_chunks with empty items.
      text_chunks = [x for x in text_chunks if x.strip() != ""]

      # clean text of escape and other unprintable chars
      text_chunks = [self.clean_text(x) for x in text_chunks]

    return text_chunks

  def chunk_pdf_slides(self, doc_name: str, doc_url: str,
                     doc_filepath: str) -> List[str]:
    """
    Process a pdf export of a slide deck into chunks for embeddings

    Args:
       doc_name: file name of document
       doc_url: remote url of document
       doc_filepath: local file path of document
    Returns:
       array where each item is an object representing a pdf page and
       contains two properties for image b64 data & text chunks 
       or None if the document could not be processed
    """
    Logger.info(f"generating index data for {doc_name}")

    # Confirm that this is a PDF
    try:
      doc_extension = doc_name.split(".")[-1]
      doc_extension = doc_extension.lower()
      if doc_extension is not "pdf":
        raise ValueError(f"File {doc_name} must be a PDF")
    except Exception as e:
      Logger.error(f"error reading doc {doc_name}: {e}")

    # Open PDF and iterate over pages
    try:
      with open(doc_filepath, "rb") as f:
        reader = PdfReader(f)
        num_pages = len(reader.pages)
        Logger.info(f"Reading pdf slide deck {doc_name} with {num_pages} pages")
        for i in range(num_pages):
          # Split page into image (PDF) and text (PDF) text files
          slide_obj = self.split_slide_page(reader.pages[i], doc_filepath)

          # Convert image to b64 and chunk text
          with open(slide_obj.text.slide_text_filename, "rb") as f:
            slide_image_b64 = b64encode(f.read()).decode("utf-8")
          slide_text_chunks = self.chunk_document(
            slide_obj.text.slide_text_filename, doc_url,
            slide_obj.text.slide_text_filename)
    except Exception as e:
      Logger.error(f"error processing doc {doc_name}: {e}")

    # Return array of page data
    return [slide_image_b64, slide_text_chunks]

  @classmethod
  def text_to_sentence_list(cls, text: str) -> List[str]:
    """
    Split text into sentences. 
    In this class we assume generic text.
    Subclasses may do additional transformation (e.g. html to text).
    """
    return text_helper.text_to_sentence_list(text)

  @classmethod
  def clean_text(cls, text: str) -> List[str]:
    """
    Produce clean text from text extracted from source document. 
    In this class we assume generic text.
    Subclasses may do additional transformation (e.g. html to text).
    """
    return text_helper.clean_text(text)

  @staticmethod
  def read_doc(doc_name: str, doc_filepath: str) -> List[str]:
    """
    Read document and return content as a list of strings

    Args:
      doc_name: name of document
      doc_filepath: local file path
    Returns:
      doc content as a list of strings
    """
    doc_extension = doc_name.split(".")[-1]
    doc_extension = doc_extension.lower()
    doc_text_list = None
    loader = None

    text_doc_extensions = ["txt", "html", "htm"]

    if doc_extension in text_doc_extensions:
      with open(doc_filepath, "r", encoding="utf-8") as f:
        doc_text = f.read()
      doc_text_list = [doc_text]
    elif doc_extension == "csv":
      loader = CSVLoader(file_path=doc_filepath)
    elif doc_extension == "pdf":
      # read PDF into array of pages
      doc_text_list = []
      with open(doc_filepath, "rb") as f:
        reader = PdfReader(f)
        num_pages = len(reader.pages)
        Logger.info(f"Reading pdf file {doc_name} with {num_pages} pages")
        for page in range(num_pages):
          doc_text_list.append(reader.pages[page].extract_text())
        Logger.info(f"Finished reading pdf file {doc_name}")
    else:
      # return None if doc type not supported
      Logger.error(
          f"Cannot read {doc_name}: unsupported extension {doc_extension}")
      pass

    if loader is not None:
      langchain_document = loader.load()
      doc_text_list = [section.page_content for section in langchain_document]

    return doc_text_list

  @staticmethod
  def split_slide_page(page: PageObject, doc_filepath: str) -> List[str]:
    """
    Read document and return content as a list of strings

    Args:
      page: a PdfReader page object representing a slide image and its text note
    Returns:
      array containing strings of the two newly created files (png and txt)
    """

    # Get file name and temp folder path
    doc_folder_i = doc_filepath.rfind("/")
    if doc_folder_i == -1:
      doc_folder = ""
    else:
      doc_folder = doc_filepath[:doc_folder_i+1]
    doc_file = doc_filepath[doc_folder_i+1:]

    # crop the top slide of the page
    slide_image_page = copy(page)
    slide_image_page.mediabox.lower_left = (page.mediabox.left,
                                page.mediabox.top - page.mediabox.height * .47)

    # create a new PDF file and add the cropped page to the new PDF file
    slide_image_pdf = PdfWriter()
    slide_image_pdf.add_page(slide_image_page)

    # write the new PDF file to a file
    slide_image_filename = "slide_" + doc_file
    slide_image_filepath = doc_folder + slide_image_filename
    with open(slide_image_filepath, "wb") as f:
      slide_image_pdf.write(f)

    # crop the bottom text content of the page
    slide_text_page = copy(page)
    slide_text_page.mediabox.upper_right = (page.mediabox.right,
                                page.mediabox.top - page.mediabox.height * .47)

    # create a new PDF file and add the cropped page to the new PDF file
    slide_text_pdf = PdfWriter()
    slide_text_pdf.add_page(slide_text_page)

    # write the new PDF file to a file
    slide_text_filename = "text_" + doc_file
    slide_text_filepath = doc_folder + "text_" + doc_file
    with open(slide_text_filepath, "wb") as f:
      slide_text_pdf.write(f)

    slide_image_obj = {
      "slide_image_filename": slide_image_filename,
      "slide_image_filepath": slide_image_filepath
    }
    slide_text_obj = {
      "slide_text_filename": slide_text_filename,
      "slide_text_filepath": slide_text_filepath
    }
    return {
      "image": slide_image_obj,
      "text": slide_text_obj
    }
