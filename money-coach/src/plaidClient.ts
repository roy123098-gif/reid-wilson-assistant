import {
  Configuration,
  CountryCode,
  PlaidApi,
  PlaidEnvironments,
  Products
} from "plaid";

export function plaidClient(): PlaidApi {
  const env = process.env.PLAID_ENV || "sandbox";
  const configuration = new Configuration({
    basePath: PlaidEnvironments[env as keyof typeof PlaidEnvironments] || PlaidEnvironments.sandbox,
    baseOptions: {
      headers: {
        "PLAID-CLIENT-ID": process.env.PLAID_CLIENT_ID || "",
        "PLAID-SECRET": process.env.PLAID_SECRET || ""
      }
    }
  });
  return new PlaidApi(configuration);
}

export function plaidProducts(): Products[] {
  return (process.env.PLAID_PRODUCTS || "transactions")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean) as Products[];
}

export function plaidCountryCodes(): CountryCode[] {
  return (process.env.PLAID_COUNTRY_CODES || "US")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean) as CountryCode[];
}

export function hasPlaidCredentials(): boolean {
  return Boolean(process.env.PLAID_CLIENT_ID && process.env.PLAID_SECRET);
}
