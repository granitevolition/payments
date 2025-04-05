/**
 * Payment processing client-side script
 * Handles real-time payment status checking and UI updates
 */

// Payment status polling
let pollingInterval;
let pollingCount = 0;
const MAX_POLLING_COUNT = 120; // Stop polling after 120 attempts (2 minutes at 1 second intervals)
const CURRENCY = 'KSH'; // Set currency to KSH

/**
 * Start polling for payment status
 * @param {string} checkoutId - The checkout ID to check
 * @param {string} statusUrl - The URL to check status at
 * @param {number} interval - Polling interval in milliseconds
 */
function startPaymentStatusPolling(checkoutId, statusUrl, interval = 1000) {
    // Clear any existing polling
    stopPaymentStatusPolling();
    
    // Reset polling count
    pollingCount = 0;
    
    // Update status message
    updateStatusMessage("Waiting for M-Pesa confirmation...");
    updateStatusTitle("Processing Payment");
    
    // Make status section visible if it's not already
    const statusSection = document.getElementById('payment-status-section');
    if (statusSection && statusSection.style.display !== 'block') {
        statusSection.style.display = 'block';
    }
    
    // Start polling
    pollingInterval = setInterval(() => {
        checkPaymentStatus(checkoutId, statusUrl);
    }, interval);
    
    console.log(`Started polling for payment status: ${checkoutId}`);
}

/**
 * Stop polling for payment status
 */
function stopPaymentStatusPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
        console.log("Stopped payment status polling");
    }
}

/**
 * Check payment status via AJAX
 * @param {string} checkoutId - The checkout ID to check
 * @param {string} statusUrl - The URL to check status at
 */
function checkPaymentStatus(checkoutId, statusUrl) {
    // Increment polling count
    pollingCount++;
    
    // Add visual feedback with dots
    const dots = ".".repeat(pollingCount % 4);
    
    // Make AJAX request
    fetch(`${statusUrl}/${checkoutId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Payment status update:", data);
            
            // Process status
            switch (data.status) {
                case 'completed':
                    // Payment successful
                    stopPaymentStatusPolling();
                    updateStatusTitle("Payment Successful!");
                    updateStatusMessage("Your payment has been processed successfully. The page will refresh in a moment to show your updated balance.");
                    updateStatusSectionStyle('success');
                    
                    // Refresh page after a delay
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);
                    break;
                    
                case 'failed':
                    // Payment failed
                    stopPaymentStatusPolling();
                    updateStatusTitle("Payment Failed");
                    updateStatusMessage(data.message || 'Payment could not be processed. Please try again.');
                    updateStatusSectionStyle('failed');
                    break;
                    
                case 'cancelled':
                    // Payment cancelled
                    stopPaymentStatusPolling();
                    updateStatusTitle("Payment Cancelled");
                    updateStatusMessage("The payment has been cancelled.");
                    updateStatusSectionStyle('cancelled');
                    break;
                    
                case 'error':
                    // Error in payment
                    stopPaymentStatusPolling();
                    updateStatusTitle("Payment Error");
                    updateStatusMessage(data.message || 'An error occurred during payment processing. Please try again.');
                    updateStatusSectionStyle('error');
                    break;
                    
                case 'pending':
                    // Still pending user action
                    updateStatusTitle("Payment Pending");
                    updateStatusMessage(`Please check your phone and approve the M-Pesa payment request${dots}`);
                    updateStatusSectionStyle('pending');
                    break;
                    
                case 'processing':
                    // Processing after user action
                    updateStatusTitle("Processing Payment");
                    updateStatusMessage(`M-Pesa is processing your payment${dots}`);
                    updateStatusSectionStyle('processing');
                    break;
                    
                case 'queued':
                    // Still in queue
                    updateStatusTitle("Payment Queued");
                    updateStatusMessage(`Your payment request is waiting to be processed${dots}`);
                    updateStatusSectionStyle('queued');
                    break;
                    
                default:
                    // Unknown status
                    updateStatusTitle("Payment Status");
                    updateStatusMessage(`Current status: ${data.status}`);
                    break;
            }
        })
        .catch(error => {
            console.error("Error checking payment status:", error);
            
            // Check if we've reached maximum polling attempts
            if (pollingCount >= MAX_POLLING_COUNT) {
                stopPaymentStatusPolling();
                updateStatusTitle("Payment Status Unknown");
                updateStatusMessage("The payment process is taking longer than expected. Please click 'Refresh Page' to check the latest status.");
                updateStatusSectionStyle('timeout');
            } else {
                // Continue polling but don't show error to user to avoid confusion
                updateStatusMessage(`Waiting for payment confirmation${dots}`);
            }
        });
}

/**
 * Update the payment status message
 * @param {string} message - The message to display
 */
function updateStatusMessage(message) {
    const messageElement = document.getElementById('payment-status-message');
    if (messageElement) {
        messageElement.textContent = message;
    }
}

/**
 * Update the payment status title
 * @param {string} title - The title to display
 */
function updateStatusTitle(title) {
    const titleElement = document.getElementById('payment-status-title');
    if (titleElement) {
        titleElement.textContent = title;
    }
}

/**
 * Update the status section styling based on status
 * @param {string} status - The status to set
 */
function updateStatusSectionStyle(status) {
    const statusSection = document.getElementById('payment-status-section');
    if (!statusSection) return;
    
    // First remove all status classes
    statusSection.classList.remove(
        'border-primary', 'border-success', 'border-danger', 'border-warning', 'border-info'
    );
    
    // Add appropriate border style
    switch(status) {
        case 'completed':
        case 'success':
            statusSection.style.borderLeftColor = '#28a745';
            break;
        case 'failed':
        case 'error':
            statusSection.style.borderLeftColor = '#dc3545';
            break;
        case 'pending':
            statusSection.style.borderLeftColor = '#ffc107';
            break;
        case 'processing':
        case 'queued':
            statusSection.style.borderLeftColor = '#17a2b8';
            break;
        case 'cancelled':
            statusSection.style.borderLeftColor = '#6c757d';
            break;
        case 'timeout':
            statusSection.style.borderLeftColor = '#fd7e14';
            break;
        default:
            statusSection.style.borderLeftColor = '#3498db';
    }
}

/**
 * Show the payment status section
 */
function showPaymentStatus() {
    const statusSection = document.getElementById('payment-status-section');
    if (statusSection) {
        statusSection.style.display = 'block';
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopPaymentStatusPolling();
});
