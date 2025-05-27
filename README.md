# WFH Monitoring System

A comprehensive work-from-home monitoring system with a React frontend and Python Flask backend.

## Project Structure

- `work-life-frontend-boost/`: React frontend application
- `backend/`: Python Flask backend application
  - `config.py`: Application configuration
  - `server.py`: Main application entry point
  - `mongodb.py`: MongoDB connection and collection setup
  - `models/`: Data models
  - `routes/`: API route handlers
  - `services/`: Business logic services
  - `utils/`: Utility functions
- `docker-compose.yml`: Docker Compose configuration for running the entire stack

## Prerequisites

- Docker and Docker Compose
- AWS account with S3 bucket for screenshots (optional)

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```
# AWS Credentials (for screenshot storage)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET=your-s3-bucket-name
```

## Running the Application

1. Build and start the containers:

```bash
docker-compose up --build
```

2. Access the application:
   - Frontend: http://localhost:8080
   - Backend API: http://localhost:5000/api

## API Endpoints

### User Endpoints
- `GET /api/users`: Get all users
- `GET /api/users/active`: Get all active users
- `GET /api/users/<username>`: Get user by username
- `GET /api/users/<username>/status`: Get user's current status

### Session Endpoints
- `POST /api/session`: Handle session events (join, leave, start/stop streaming)
- `GET /api/sessions/<username>`: Get sessions for a specific user

### Activity Endpoints
- `POST /api/activity`: Record user activity
- `GET /api/activities/<username>`: Get activities for a specific user
- `GET /api/app-usage/<username>`: Get app usage statistics for a user
- `GET /api/daily-summary/<username>`: Get daily summary for a user

### Screenshot Endpoints
- `POST /api/screenshot`: Upload a screenshot
- `GET /api/screenshots/<username>`: Get screenshots for a user

## Troubleshooting

If you encounter any issues with the backend API, check the Docker logs:

```bash
docker-compose logs backend
```

For frontend issues:

```bash
docker-compose logs frontend
```