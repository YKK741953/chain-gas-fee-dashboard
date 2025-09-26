# Infura RPC Quick Reference

Set the shared credentials in `.env.local`:

```
INFURA_PROJECT_ID=<YOUR-PROJECT-ID>
INFURA_PROJECT_SECRET=<OPTIONAL-SECRET>
```

With these values present, the backend auto-generates network URLs of the form:

```
https://<network>.infura.io/v3/<INFURA_PROJECT_ID>
```

Network slugs used in this project:

- `mainnet` (Ethereum)
- `polygon-mainnet`
- `arbitrum-mainnet`
- `optimism-mainnet`
- `avalanche-mainnet`
- `linea-mainnet`

If you prefer to override specific chains (e.g., using Alchemy), set the full URL manually in `.env.local`:

```
RPC_ETHEREUM_URL=https://eth-mainnet.g.alchemy.com/v2/<API-KEY>
```

Manual overrides always take precedence over the auto-generated Infura URLs.
