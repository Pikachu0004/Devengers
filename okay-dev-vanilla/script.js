// Register GSAP ScrollTrigger if available
if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
    gsap.registerPlugin(ScrollTrigger);

    const isMobilePhone = window.innerWidth <= 768 || window.matchMedia('(max-width: 768px)').matches;

    function forceMobileElementsVisible() {
        const visibleElements = document.querySelectorAll('.nav-feature-card, .pricing-card, #gallery-section, .bento-card, .member-card, .job-row, .card, .floating-image, .hide-on-scroll');
        visibleElements.forEach(el => {
            el.style.opacity = '1';
            el.style.transform = 'none';
            el.style.visibility = 'visible';
        });
    }

    // Only activate heavy scroll triggers and opacity collapses on desktop/tablet (> 768px).
    // On phones (<= 768px), all cards and sections remain 100% visible, solid, and non-distorted.
    if (!isMobilePhone) {
        // Hero cards convergence animation
        const floatingImages = gsap.utils.toArray('.floating-image');
        let tl = gsap.timeline({
            scrollTrigger: {
                trigger: ".hero-bg-grid",
                start: "top top",
                end: "center top",
                scrub: 0.2,
            }
        });

        floatingImages.forEach((img) => {
            const rect = img.getBoundingClientRect();
            const centerX = window.innerWidth / 2;
            const centerY = window.innerHeight / 2;
            
            const dirX = (rect.left + rect.width / 2) - centerX;
            const dirY = (rect.top + rect.height / 2) - centerY;
            
            const distance = 220;
            const length = Math.sqrt(dirX * dirX + dirY * dirY) || 1;
            const moveX = -(dirX / length) * distance;
            const moveY = -(dirY / length) * distance;

            tl.to(img, {
                x: moveX,
                y: moveY,
                opacity: 0,
                scale: 0.5,
                ease: "power2.inOut"
            }, 0); 
        });

        tl.to(".hide-on-scroll", {
            opacity: 0,
            y: -30,
            ease: "power2.inOut"
        }, 0);

        tl.to("#builders-text", {
            scale: 1.2,
            y: 50,
            ease: "power2.inOut"
        }, 0);

        // 3D Rolling/Folding effect for Gallery Section on desktop only
        gsap.set("#gallery-section", { transformPerspective: 1200 });

        gsap.to("#gallery-section", {
            scrollTrigger: {
                trigger: "#social-section",
                start: "top bottom",
                end: "top center",
                scrub: 0,
            },
            scale: 0.85,           
            rotationX: 15,         
            y: 60,                
            opacity: 0.1,
            transformOrigin: "center bottom",
            ease: "power1.inOut"
        });

        // Massive background text parallax in Purple section
        gsap.to("#bg-text-okaydev", {
            scrollTrigger: {
                trigger: "#social-section",
                start: "top bottom",
                end: "bottom top",
                scrub: true
            },
            x: "-25%",
            ease: "none"
        });

        // Section 4: Navbar Feature Cards Stagger Entrance (Stays visible once played)
        gsap.fromTo(".nav-feature-card", 
            { y: 35, opacity: 0, scale: 0.97 },
            {
                scrollTrigger: {
                    trigger: "#projects-section",
                    start: "top 80%",
                    toggleActions: "play none none none",
                },
                y: 0,
                opacity: 1,
                scale: 1,
                duration: 0.6,
                stagger: 0.08,
                ease: "power3.out"
            }
        );

        // Section 9: Pricing Cards Stagger (Stays visible once played)
        gsap.from(".pricing-card", {
            scrollTrigger: {
                trigger: "#pricing-section",
                start: "top 75%",
                toggleActions: "play none none none",
            },
            y: 60,
            opacity: 0,
            duration: 0.7,
            stagger: 0.15,
            ease: "power2.out"
        });
    } else {
        // On mobile: immediately ensure all cards and sections have full opacity and clean transforms
        forceMobileElementsVisible();
        document.addEventListener('DOMContentLoaded', forceMobileElementsVisible);
    }
}

// Section 10: FAQ Interactive Accordion
document.addEventListener('DOMContentLoaded', () => {
    const faqTriggers = document.querySelectorAll('.faq-trigger');
    faqTriggers.forEach((trigger) => {
        trigger.addEventListener('click', () => {
            const item = trigger.closest('.faq-item');
            const content = item.querySelector('.faq-content');
            const icon = trigger.querySelector('.faq-icon');
            const isOpen = !content.classList.contains('hidden');

            // Close all other items for a clean single-open accordion feel
            document.querySelectorAll('.faq-item').forEach((otherItem) => {
                if (otherItem !== item) {
                    const otherContent = otherItem.querySelector('.faq-content');
                    const otherIcon = otherItem.querySelector('.faq-icon');
                    if (otherContent) otherContent.classList.add('hidden');
                    if (otherIcon) {
                        otherIcon.classList.remove('rotate-45');
                    }
                }
            });

            // Toggle current item
            if (isOpen) {
                content.classList.add('hidden');
                icon.classList.remove('rotate-45');
                trigger.setAttribute('aria-expanded', 'false');
            } else {
                content.classList.remove('hidden');
                icon.classList.add('rotate-45');
                trigger.setAttribute('aria-expanded', 'true');
            }
        });
    });
});

