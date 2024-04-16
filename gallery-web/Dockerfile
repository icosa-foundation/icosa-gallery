# Use the specified version of Node.js
FROM node:16.14.2

# Set the working directory in the container
WORKDIR /usr/src/app

# Clone the repository
RUN git clone https://github.com/icosa-foundation/gallery-web .
RUN git checkout open-brush-integration


# Install Node.js dependencies
RUN npm install

# Expose the port the app runs on
EXPOSE 3000

# Start the application
CMD ["npm", "start"]
