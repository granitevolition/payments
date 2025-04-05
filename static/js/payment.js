/**
 * Payment processing client-side script
 * Handles real-time payment status checking and UI updates
 */

// Payment status polling
let pollingInterval;
let pollingCount = 0;
const MAX_POLLING_COUNT = 120; // Stop polling after 120 attempts (2 minutes at 1 second intervals)

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
    
    // Update status indicators
    updateStatusMessage("Waiting for payment confirmation...");
    updateStatusIndicator("pending");
    
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
    updateStatusMessage(`Waiting for payment confirmation${dots}`);
    
    // Check if we've reached maximum polling attempts
    if (pollingCount >= MAX_POLLING_COUNT) {
        stopPaymentStatusPolling();
        updateStatusMessage("Payment processing timed out. Please check your dashboard for payment status.");
        updateStatusIndicator("timeout");
        
        // Show timeout message and redirect button
        showTimeoutMessage();
        return;
    }
    
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
                    updateStatusMessage("Payment successful! Redirecting to success page...");
                    updateStatusIndicator("success");
                    
                    // Redirect to success page
                    setTimeout(() => {
                        window.location.href = `/payment-success/${checkoutId}`;
                    }, 1500);
                    break;
                    
                case 'failed':
                case 'cancelled':
                case 'error':
                    // Payment failed
                    stopPaymentStatusPolling();
                    updateStatusMessage(`Payment failed: ${data.message || 'Unknown error'}`);
                    updateStatusIndicator("failed");
                    
                    // Redirect to failure page
                    setTimeout(() => {
                        window.location.href = `/payment-failed/${checkoutId}`;
                    }, 1500);
                    break;
                    
                case 'pending':
                case 'processing':
                    // Still processing, continue polling
                    updateStatusMessage(`Waiting for payment confirmation${dots}`);
                    updateStatusIndicator("pending");
                    break;
                    
                default:
                    // Unknown status
                    updateStatusMessage(`Unknown status: ${data.status}`);
                    updateStatusIndicator("unknown");
                    break;
            }
        })
        .catch(error => {
            console.error("Error checking payment status:", error);
            updateStatusMessage(`Error checking payment status. Retrying...`);
        });
}

/**
 * Update the payment status message
 * @param {string} message - The message to display
 */
function updateStatusMessage(message) {
    const statusElement = document.getElementById('payment-status-message');
    if (statusElement) {
        statusElement.textContent = message;
    }
}

/**
 * Update the payment status indicator
 * @param {string} status - The status to display
 */
function updateStatusIndicator(status) {
    const indicatorElement = document.getElementById('payment-status-indicator');
    if (indicatorElement) {
        // Remove all status classes
        indicatorElement.classList.remove('status-pending', 'status-success', 'status-failed', 'status-timeout', 'status-unknown');
        
        // Add appropriate class
        indicatorElement.classList.add(`status-${status}`);
    }
}

/**
 * Show timeout message
 */
function showTimeoutMessage() {
    const timeoutElement = document.getElementById('payment-timeout-message');
    if (timeoutElement) {
        timeoutElement.style.display = 'block';
    }
}

/**
 * Cancel the current payment
 * @param {string} checkoutId - The checkout ID to cancel
 * @param {string} cancelUrl - The URL to cancel payment at
 */
function cancelPayment(checkoutId, cancelUrl) {
    if (confirm('Are you sure you want to cancel this payment?')) {
        stopPaymentStatusPolling();
        window.location.href = `${cancelUrl}/${checkoutId}`;
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopPaymentStatusPolling();
});
