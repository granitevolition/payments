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
    
    // Update status indicators on notification in dashboard
    updateStatusNotification("Processing Payment", "Waiting for payment confirmation...");
    
    // Show notification if it's not already visible
    const notificationEl = document.getElementById('payment-notification');
    if (notificationEl && notificationEl.style.display !== 'block') {
        notificationEl.style.display = 'block';
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
    updateStatusNotification(null, `Waiting for payment confirmation${dots}`);
    
    // Check if we've reached maximum polling attempts
    if (pollingCount >= MAX_POLLING_COUNT) {
        stopPaymentStatusPolling();
        updateStatusNotification("Payment Timeout", "Payment processing timed out. Please check your dashboard for the latest status.");
        
        // Automatically refresh page after 3 seconds
        setTimeout(() => {
            window.location.reload();
        }, 3000);
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
                    updateStatusNotification("Payment Successful!", "Your payment has been processed successfully. Refreshing page...");
                    
                    // Refresh page to show updated balance
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                    break;
                    
                case 'failed':
                case 'cancelled':
                case 'error':
                    // Payment failed
                    stopPaymentStatusPolling();
                    updateStatusNotification("Payment Failed", data.message || 'Payment could not be processed. Please try again.');
                    
                    // Refresh page after a delay
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);
                    break;
                    
                case 'pending':
                    // Still pending user action
                    updateStatusNotification("Payment Pending", `Please check your phone and approve the M-Pesa payment${dots}`);
                    break;
                    
                case 'processing':
                    // Processing after user action
                    updateStatusNotification("Processing Payment", `M-Pesa is processing your payment${dots}`);
                    break;
                    
                case 'queued':
                    // Still in queue
                    updateStatusNotification("Payment Queued", `Your payment request is in queue${dots}`);
                    break;
                    
                default:
                    // Unknown status
                    updateStatusNotification("Unknown Status", `Current status: ${data.status}`);
                    break;
            }
        })
        .catch(error => {
            console.error("Error checking payment status:", error);
            updateStatusNotification(null, `Error checking payment status. Retrying...`);
        });
}

/**
 * Update the payment status notification in the dashboard
 * @param {string|null} title - The title to display (null to keep existing)
 * @param {string} message - The message to display
 */
function updateStatusNotification(title, message) {
    const titleElement = document.getElementById('payment-status-title');
    const messageElement = document.getElementById('payment-status-message');
    
    if (messageElement) {
        messageElement.textContent = message;
    }
    
    if (title && titleElement) {
        titleElement.textContent = title;
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
