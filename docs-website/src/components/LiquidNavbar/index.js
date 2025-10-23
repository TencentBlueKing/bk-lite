import { useEffect } from 'react';
import './styles.module.css';

export default function LiquidNavbar() {
  useEffect(() => {
    let ticking = false;
    
    function updateNavbar() {
      const navbar = document.querySelector('.navbar');
      if (!navbar) return;
      
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      
      if (scrollTop > 50) {
        navbar.classList.add('navbar--scrolled');
      } else {
        navbar.classList.remove('navbar--scrolled');
      }
      
      ticking = false;
    }
    
    function requestTick() {
      if (!ticking) {
        requestAnimationFrame(updateNavbar);
        ticking = true;
      }
    }
    
    // 初始检查
    updateNavbar();
    
    // 添加滚动监听器
    window.addEventListener('scroll', requestTick, { passive: true });
    
    return () => {
      window.removeEventListener('scroll', requestTick);
    };
  }, []);
  
  return null;
}
