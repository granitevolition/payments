// Main JavaScript for Lipia Subscription Service

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Auto-close alerts after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            const closeButton = new bootstrap.Alert(alert);
            closeButton.close();
        });
    }, 5000);
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Phone number formatter for registration form
    const phoneInput = document.querySelector('input[name="phone_number"]');
    if (phoneInput) {
        phoneInput.addEventListener('input', function(e) {
            let value = e.target.value.replace(/\D/g, '');
            
            // Ensure the phone number starts with 0
            if (value.length > 0 && value[0] !== '0') {
                value = '0' + value;
            }
            
            // Ensure the phone number starts with 07
            if (value.length > 1 && value[1] !== '7') {
                value = '07' + value.substring(2);
            }
            
            // Limit to 10 digits
            if (value.length > 10) {
                value = value.substring(0, 10);
            }
            
            e.target.value = value;
        });
    }
    
    // Confirm payment submission
    const paymentLinks = document.querySelectorAll('a[href*="process_payment"]');
    if (paymentLinks.length > 0) {
        paymentLinks.forEach(function(link) {
            link.addEventListener('click', function(e) {
                const confirm = window.confirm('Are you sure you want to make this payment?');
                if (!confirm) {
                    e.preventDefault();
                }
            });
        });
    }
    
    // Word usage form validation
    const useWordsForm = document.querySelector('form[action*="use_words"]');
    if (useWordsForm) {
        useWordsForm.addEventListener('submit', function(e) {
            const wordsInput = document.querySelector('input[name="words_to_use"]');
            const wordsValue = parseInt(wordsInput.value);
            const wordsRemaining = parseInt(document.querySelector('strong:contains("words remaining")').textContent);
            
            if (isNaN(wordsValue) || wordsValue <= 0) {
                e.preventDefault();
                alert('Please enter a positive number of words to use.');
                return false;
            }
            
            if (wordsValue > wordsRemaining) {
                e.preventDefault();
                alert('You don\'t have enough words remaining. Please purchase more words or enter a smaller value.');
                return false;
            }
        });
    }
});
