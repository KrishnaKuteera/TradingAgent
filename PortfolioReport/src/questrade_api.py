#!/usr/bin/env python3
"""Questrade API client for fetching live portfolio data."""

import requests
import json
from pathlib import Path
from datetime import datetime
import pandas as pd


class QuestradeAPI:
    def __init__(self, refresh_token_file: str = "ChanduAPITracker"):
        """Initialize API client with refresh token."""
        self.token_file = refresh_token_file
        with open(refresh_token_file, 'r') as f:
            self.refresh_token = f.read().strip()

        self.access_token = None
        self.api_server = None
        self.accounts = {}
        self.authenticate()

    def authenticate(self):
        """Exchange refresh token for access token (valid 30 minutes)."""
        url = "https://login.questrade.com/oauth2/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }

        response = requests.post(url, params=params)
        if response.status_code != 200:
            raise Exception(f"Authentication failed: {response.text}")

        tokens = response.json()
        self.access_token = tokens['access_token']
        self.api_server = tokens['api_server']

        # IMPORTANT: Save the new refresh token for next time
        self.refresh_token = tokens['refresh_token']
        with open(self.token_file, 'w') as f:
            f.write(self.refresh_token)

        print("✓ Authenticated with Questrade API")

    def get_accounts(self):
        """Fetch list of accounts."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.api_server}v1/accounts"

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get accounts: {response.text}")

        self.accounts = {acct['number']: acct for acct in response.json()['accounts']}
        return self.accounts

    def get_balances(self, account_num: str) -> dict:
        """Fetch account balances."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.api_server}v1/accounts/{account_num}/balances"

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get balances for {account_num}: {response.text}")

        return response.json()

    def get_positions(self, account_num: str) -> dict:
        """Fetch account positions/holdings."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.api_server}v1/accounts/{account_num}/positions"

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get positions for {account_num}: {response.text}")

        return response.json()

    def get_activities(self, account_num: str, start_time: int = None) -> dict:
        """Fetch transaction history. startTime is Unix timestamp in milliseconds."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.api_server}v1/accounts/{account_num}/activities"

        # Default to last 30 days if no startTime provided (Questrade default window)
        if not start_time:
            from datetime import timedelta
            thirty_days_ago = datetime.now() - timedelta(days=30)
            start_time = int(thirty_days_ago.timestamp() * 1000)

        params = {'startTime': start_time}

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            raise Exception(f"Failed to get activities for {account_num}: {response.text}")

        return response.json()

    def get_all_data(self):
        """Fetch all data for all accounts."""
        self.get_accounts()

        data = {}
        for acct_num, acct_info in self.accounts.items():
            print(f"\nFetching data for {acct_info['type']} ({acct_num})...")

            activities = None
            try:
                activities = self.get_activities(acct_num)
            except Exception as e:
                print(f"  Warning: Could not fetch activities: {e}")

            data[acct_num] = {
                'info': acct_info,
                'balances': self.get_balances(acct_num),
                'positions': self.get_positions(acct_num),
                'activities': activities
            }
            print(f"  ✓ Balances and positions fetched")

        return data


def main():
    """Test the API client."""
    api = QuestradeAPI()
    data = api.get_all_data()

    print("\n" + "=" * 80)
    print("DATA SUMMARY")
    print("=" * 80)

    for acct_num, acct_data in data.items():
        info = acct_data['info']
        balances = acct_data['balances']['perCurrencyBalances'][0]  # Get first currency
        positions = acct_data['positions']['positions']

        print(f"\n{info['type']} ({acct_num}):")
        print(f"  Cash (CAD): ${balances.get('cash', 0):,.2f}")
        print(f"  Market Value: ${balances.get('marketValue', 0):,.2f}")
        print(f"  Positions: {len(positions)}")

        if positions:
            for pos in positions[:3]:  # Show first 3
                print(f"    - {pos['symbol']}: {pos['openQuantity']} shares")


if __name__ == "__main__":
    main()
