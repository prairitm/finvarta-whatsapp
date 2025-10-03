# Railway Deployment Guide

This guide will help you deploy the FinVarta WhatsApp Processor FastAPI application to Railway.

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **GitHub Repository**: Push your code to GitHub
3. **Environment Variables**: Have your API keys ready

## Deployment Steps

### 1. Prepare Your Repository

Make sure your repository contains:
- `fastapi_endpoint.py` - Main FastAPI application
- `twilio_whatsapp_processor.py` - Core processing logic
- `requirements.txt` - Python dependencies
- `Procfile` - Railway process configuration
- `railway.json` - Railway deployment configuration

### 2. Deploy to Railway

#### Option A: Deploy from GitHub (Recommended)

1. **Connect GitHub**:
   - Go to [Railway Dashboard](https://railway.app/dashboard)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

2. **Configure Environment Variables**:
   - In your Railway project dashboard
   - Go to "Variables" tab
   - Add the following environment variables:

   ```
   OPENAI_API_KEY=your_openai_api_key_here
   TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
   TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
   TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
   WHATSAPP_RECIPIENTS=+1234567890,+0987654321
   OPENAI_MODEL=gpt-3.5-turbo
   OPENAI_MAX_TOKENS=1000
   OPENAI_TEMPERATURE=0.3
   OPENAI_MAX_TEXT_LENGTH=12000
   DELAY_BETWEEN_REQUESTS=2
   ```

3. **Deploy**:
   - Railway will automatically detect the Python application
   - It will install dependencies from `requirements.txt`
   - The application will start using the `Procfile`

#### Option B: Deploy using Railway CLI

1. **Install Railway CLI**:
   ```bash
   npm install -g @railway/cli
   ```

2. **Login to Railway**:
   ```bash
   railway login
   ```

3. **Initialize and Deploy**:
   ```bash
   railway init
   railway up
   ```

### 3. Configure Environment Variables

In your Railway project dashboard:

1. Go to your project
2. Click on "Variables" tab
3. Add the following variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key | `sk-...` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `AC...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `your_auth_token` |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp number | `whatsapp:+14155238886` |
| `WHATSAPP_RECIPIENTS` | Comma-separated phone numbers | `+1234567890,+0987654321` |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-3.5-turbo` |
| `OPENAI_MAX_TOKENS` | Max tokens for OpenAI | `1000` |
| `OPENAI_TEMPERATURE` | OpenAI temperature | `0.3` |
| `OPENAI_MAX_TEXT_LENGTH` | Max text length | `12000` |
| `DELAY_BETWEEN_REQUESTS` | Delay between requests | `2` |

### 4. Test Your Deployment

Once deployed, you can test your API:

1. **Health Check**:
   ```bash
   curl https://your-app-name.railway.app/health
   ```

2. **Process Announcement**:
   ```bash
   curl -X POST https://your-app-name.railway.app/process \
     -H "Content-Type: application/json" \
     -d '{"use_sample_data": true}'
   ```

3. **API Documentation**:
   Visit `https://your-app-name.railway.app/docs` for interactive API documentation

## Configuration Files

### Procfile
```
web: uvicorn fastapi_endpoint:app --host 0.0.0.0 --port $PORT
```

### railway.json
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn fastapi_endpoint:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

## Monitoring and Logs

1. **View Logs**: In Railway dashboard, go to "Deployments" tab to view logs
2. **Health Monitoring**: Railway will automatically monitor the `/health` endpoint
3. **Auto-restart**: The app will restart automatically on failure

## API Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `POST /process` - Process announcement and send WhatsApp message

## Troubleshooting

### Common Issues

1. **Environment Variables Not Set**:
   - Check Railway Variables tab
   - Ensure all required variables are set

2. **Build Failures**:
   - Check Railway logs for dependency issues
   - Verify `requirements.txt` has correct versions

3. **Runtime Errors**:
   - Check application logs in Railway dashboard
   - Verify all environment variables are correctly set

4. **WhatsApp Not Sending**:
   - Verify Twilio credentials
   - Check WhatsApp recipients format
   - Ensure Twilio WhatsApp is properly configured

### Getting Help

- Railway Documentation: [docs.railway.app](https://docs.railway.app)
- Railway Discord: [discord.gg/railway](https://discord.gg/railway)
- Check Railway logs for specific error messages

## Cost Considerations

- Railway offers a free tier with limited usage
- Monitor your usage in the Railway dashboard
- Consider upgrading to paid plans for production use

## Security Notes

- Never commit `.env` files to version control
- Use Railway's environment variables for sensitive data
- Regularly rotate your API keys
- Monitor your API usage and costs
