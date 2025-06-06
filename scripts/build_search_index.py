#  Copyright 2021 Collate
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""
Build Algolia index based on the content folder
"""

import json
import logging
import os
import re
from typing import Optional, List
from pathlib import Path

import frontmatter

from pydantic import BaseModel, Field
from algoliasearch.search_client import SearchClient


ALGOLIA_CLIENT_ID = os.environ.get("ALGOLIA_CLIENT_ID")
ALGOLIA_ADMIN_KEY = os.environ.get("ALGOLIA_ADMIN_KEY")
ALGOLIA_INDEX = os.environ.get("ALGOLIA_INDEX")

CONTENT_REGEX = re.compile(r"<(.*?)>", re.DOTALL | re.MULTILINE)

EXCLUDED_FILES = {"gdpr-banner", "menu"}
EXCLUDED_DIRS = {"main-concepts"}


class AlgoliaDoc(BaseModel):
    objectID: str = Field(
        ..., description="Internal Algolia ID. Generated from our slug."
    )
    title: str = Field(..., description="Page title, taken from header.")
    description: Optional[str] = Field(
        ..., description="Page description, taken from header"
    )
    categories: List[str] = Field(
        ..., description="Page categories, generated splitting the slug"
    )
    content: str = Field(..., description="Page content")


def get_page_content(content: str) -> str:
    """
    Get and clean the page content. We want to get rid of
    HTML tags and markdown formatting
    """
    return CONTENT_REGEX.sub("", content, 0).replace("\n", "").replace("#", "")


def get_algolia_doc_from_file(file: Path) -> Optional[AlgoliaDoc]:
    """
    Given a markdown file, search the metadata of the
    header and return the AlgoliaDoc
    """
    try:
        with open(file.absolute()) as f:
            page = frontmatter.load(f)

            # Skip pages that are Collate specific
            if page.metadata.get("collate"):
                return None

            return AlgoliaDoc(
                objectID=page.metadata["slug"],
                title=page.metadata["title"],
                description=page.metadata.get("description"),
                categories=page.metadata["slug"].lstrip("/").split("/"),
                content=get_page_content(page.content),
            )
    except KeyError as err:
        logging.warning(f"Error processing file at {file} - [{err}]. Skipping...")
        return None


def build_algolia_index_name(version: str) -> str:
    """Build dynamic index name based on version"""
    return f"{ALGOLIA_INDEX}-{version}"


def build_index(version: Path):
    """
    Picks up all content files and replaces
    the algolia index.

    We are not indexing root files of the `content` dir, such as
    menu or index.
    """

    results = []
    for file in version.rglob("*.[mM][dD]"):
        if file.stem not in EXCLUDED_FILES:
            if not any(substring in str(file) for substring in EXCLUDED_DIRS):
                if file.stat().st_size > 100000:  # Check file size
                    with open(file, "r+b") as f:  # Open file for reading and writing
                        f.truncate(100000)
                results.append(file)

    algolia_docs = (get_algolia_doc_from_file(page) for page in results)
    docs = [json.loads(doc.json()) for doc in algolia_docs if doc]

    # Start the API client
    # https://www.algolia.com/doc/api-client/getting-started/instantiate-client-index/
    client = SearchClient.create(ALGOLIA_CLIENT_ID, ALGOLIA_ADMIN_KEY)

    # Create an index (or connect to it, if an index with the name `ALGOLIA_INDEX_NAME` already exists)
    # https://www.algolia.com/doc/api-client/getting-started/instantiate-client-index/#initialize-an-index
    index = client.init_index(build_algolia_index_name(version.name))

    # Replace the index with new objects
    # https://www.algolia.com/doc/api-reference/api-methods/replace-all-objects/
    index.replace_all_objects(docs, {"safe": False})


def build_indexes() -> None:
    """Build one index for each version"""
    versions = [v for v in list(Path("content").glob("v*"))]
    for version in versions:
        build_index(version=version)


if __name__ == "__main__":
    build_indexes()
