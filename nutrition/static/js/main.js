document.addEventListener('DOMContentLoaded', function() {
    // Form validation enhancements
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const inputs = form.querySelectorAll('input[required], select[required]');
            let isValid = true;
            
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    input.classList.add('border-red-500');
                    isValid = false;
                } else {
                    input.classList.remove('border-red-500');
                }
            });
        });
    });
    
    // Input field interactions
    const inputFields = document.querySelectorAll('input, select');
    inputFields.forEach(field => {
        field.addEventListener('focus', function() {
            this.parentElement.classList.add('ring-2', 'ring-indigo-200');
        });
        
        field.addEventListener('blur', function() {
            this.parentElement.classList.remove('ring-2', 'ring-indigo-200');
        });
    });
    
    // Toggle password visibility
    const togglePasswordButtons = document.querySelectorAll('.toggle-password');
    togglePasswordButtons.forEach(button => {
        button.addEventListener('click', function() {
            const input = this.previousElementSibling;
            const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
            input.setAttribute('type', type);
            this.querySelector('i').classList.toggle('fa-eye');
            this.querySelector('i').classList.toggle('fa-eye-slash');
        });
    });
    
    // Animate meal cards on page load
    const mealCards = document.querySelectorAll('.meal-card');
    mealCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.animationDelay = `${index * 0.1}s`;
        card.classList.add('animate-fadeIn');
    });
    
    // Nutrition facts tabs
    const nutritionTabs = document.querySelectorAll('.nutrition-tab');
    const nutritionContents = document.querySelectorAll('.nutrition-content');
    
    if (nutritionTabs.length > 0) {
        nutritionTabs.forEach(tab => {
            tab.addEventListener('click', function() {
                const target = this.getAttribute('data-target');
                
                // Update active tab
                nutritionTabs.forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                
                // Show targeted content
                nutritionContents.forEach(content => {
                    content.classList.add('hidden');
                    if (content.id === target) {
                        content.classList.remove('hidden');
                    }
                });
            });
        });
    }
    
    // Save meal button animation
    const saveButtons = document.querySelectorAll('.save-meal-btn');
    saveButtons.forEach(button => {
        button.addEventListener('click', function() {
            this.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Saving...';
        });
    });
});