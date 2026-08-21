from google_play_scraper import Sort, reviews
from pydantic import BaseModel, ConfigDict
from typing import Any, List, Optional
from pymongo import MongoClient
import pandas as pd
import time, json
import warnings
warnings.filterwarnings('ignore')


class Config(BaseModel):
    """
    Pydantic class - configuration settings for the Google Play Store review scraper and MongoDB writer.

    @args:
        app_id: The unique identifier of the app on the Google Play Store.
        batch_size: Number of reviews to fetch in each batch.
        target: Total number of reviews to scrape.
        rate_limit: Waiting time between HTTP requests.
        mongo_url: MongoDB connection URL.
        database_name: Name of the MongoDB database.
        collection_name: Name of the MongoDB collection.
        write: Boolean value indicating whether reviews should be written to MongoDB.
    """
    app_id: str
    batch_size: int
    target: int
    rate_limit: float
    mongo_url: str
    database_name: str
    collection_name: str
    write: bool


class ReviewScrapper(Config):
    """
    Scraper for extracting reviews from the Google Play Store. Inherits the configuration parameters required for scraping from the Config class 
    and provides a method to retrieve reviews in batches.

    @args:
        app_id: The unique identifier of the app on the Google Play Store.
        batch_size: Number of reviews to fetch in each batch.
        target: Total number of reviews to scrape.
        rate_limit: Waiting time between HTTP requests.

    @methods:
        scrape_reviews: Scrapes reviews from the Google Play Store and returns them as a single pandas DataFrame.
    
    @returns:
        merged_df: Pandas DataFrame containing all scraped reviews.
    """

    def scrape_reviews(self) -> pd.DataFrame:
        """ Scrape reviews from the Google Play Store. """

        all_reviews: List[pd.DataFrame] = []
        total: int = 0
        next_token: Optional[Any] = None

        while total < self.target:

            # Scrape reviews in batches
            batch_reviews, next_token = reviews(self.app_id, lang = "en", country = "us", sort = Sort.NEWEST, count=self.batch_size, continuation_token = next_token) # type: ignore

            if not batch_reviews:
                print("No more reviews available.")
                break

            # Store the scraped batch in a DataFrame
            batch_df: pd.DataFrame = pd.DataFrame(batch_reviews)
            all_reviews.append(batch_df)

            # Increment count of extracted reviews
            total += len(batch_df)
            print(f"Collected {total:,} reviews")

            # Stop if there are no more reviews
            if next_token is None:
                print("Reached end of available reviews.")
                break

            # Wait before making the next request
            time.sleep(self.rate_limit)

        # Merge all scraped DataFrames
        if all_reviews:
            merged_df = pd.concat(all_reviews, ignore_index=True)
        else:
            merged_df = pd.DataFrame()

        return merged_df


class MongoDBWriter(BaseModel):
    """
    Writer for storing scraped Google Play Store reviews in MongoDB. Uses the MongoDB configuration parameters to establish a connection, convert the review DataFrame 
    into MongoDB-compatible records, and insert the records into the collection.

    @args:
        mongo_url: MongoDB connection URL.
        database_name: Name of the MongoDB database.
        collection_name: Name of the MongoDB collection.
        review_df: Pandas DataFrame containing the review data.
        write: Boolean value indicating whether reviews should be written to MongoDB.

    @methods:
        write_reviews_to_mongodb: Writes the review DataFrame records to MongoDB.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    mongo_url: str
    database_name: str
    collection_name: str
    review_df: pd.DataFrame
    write: bool

    def write_reviews_to_mongodb(self) -> None:
        """ Write reviews from a pandas DataFrame to MongoDB. """

        # Establish connection to MongoDB
        client = MongoClient(self.mongo_url)

        # Select the database and collection
        db = client[self.database_name]
        collection = db[self.collection_name]

        # Convert DataFrame rows into a list of dictionaries
        records = self.review_df.astype(object).where(pd.notna(self.review_df), None).to_dict(orient="records")

        # Insert records into MongoDB if the DataFrame is not empty and writing is enabled
        if records and self.write:
            collection.insert_many(records)

        # Close the MongoDB connection
        client.close()



if __name__ == "__main__":
    # Load configuration from JSON file
    with open("config.json", "r") as file:
        config_data = json.load(file)

    # Validate configuration using Pydantic
    config = Config(**config_data)

    # Create scraper using the configuration
    scraper = ReviewScrapper(**config.model_dump())

    # Scrape reviews
    reviews_df = scraper.scrape_reviews()

    # Create MongoDB writer using the configuration and scraped reviews
    writer = MongoDBWriter(**config.model_dump(), review_df = reviews_df)

    # Write reviews to MongoDB
    writer.write_reviews_to_mongodb()
    
    print('Scraping completed!')