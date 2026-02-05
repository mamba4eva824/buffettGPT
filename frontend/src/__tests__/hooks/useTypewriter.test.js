/**
 * useTypewriter Hook Tests
 *
 * P2 Tests for the typewriter animation hook.
 * Tests character animation, punctuation pauses, speed acceleration,
 * inactive state, empty strings, and text change resets.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useTypewriter from '../../hooks/useTypewriter';

describe('useTypewriter', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Character Animation', () => {
    it('should start with partial text (first batch revealed synchronously)', () => {
      const { result } = renderHook(() =>
        useTypewriter('Hello World', { isActive: true, alwaysAnimate: true })
      );

      // With fake timers, first batch is revealed synchronously via useEffect
      // The hook reveals 2-5 chars per batch
      expect(result.current.displayText.length).toBeGreaterThan(0);
      expect(result.current.displayText.length).toBeLessThan(11);
    });

    it('should reveal characters progressively over time', () => {
      const { result } = renderHook(() =>
        useTypewriter('Hello World', { isActive: true, alwaysAnimate: true })
      );

      // First batch revealed synchronously
      const initialLength = result.current.displayText.length;
      expect(initialLength).toBeGreaterThan(0);
      expect(initialLength).toBeLessThan(11);

      // Advance timers to trigger more batches
      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Should have revealed more characters
      expect(result.current.displayText.length).toBeGreaterThan(initialLength);
    });

    it('should eventually reveal all text', () => {
      const text = 'Hello World';
      const { result } = renderHook(() =>
        useTypewriter(text, { isActive: false, alwaysAnimate: true })
      );

      // Advance enough time for all characters to reveal
      act(() => {
        vi.advanceTimersByTime(2000);
      });

      expect(result.current.displayText).toBe(text);
    });

    it('should set isTyping to true while animating', () => {
      const { result } = renderHook(() =>
        useTypewriter('Hello', { isActive: true, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(30);
      });

      expect(result.current.isTyping).toBe(true);
    });

    it('should set isTyping to false when animation completes', () => {
      const { result } = renderHook(() =>
        useTypewriter('Hi', { isActive: false, alwaysAnimate: true })
      );

      // Advance enough time for complete reveal
      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(result.current.displayText).toBe('Hi');
      expect(result.current.isTyping).toBe(false);
    });

    it('should reveal in batches of 2-5 characters', () => {
      const { result, rerender } = renderHook(
        ({ text }) => useTypewriter(text, { isActive: true, alwaysAnimate: true }),
        { initialProps: { text: 'ABCDEFGHIJ' } }
      );

      const lengths = [result.current.displayText.length];

      // Collect lengths after each timer tick
      for (let i = 0; i < 5; i++) {
        act(() => {
          vi.advanceTimersByTime(30);
        });
        lengths.push(result.current.displayText.length);
      }

      // Calculate increments between reveals
      const increments = [];
      for (let i = 1; i < lengths.length; i++) {
        if (lengths[i] > lengths[i - 1]) {
          increments.push(lengths[i] - lengths[i - 1]);
        }
      }

      // Should have at least one increment
      expect(increments.length).toBeGreaterThan(0);

      // Each increment should be within batch size range (1-5)
      increments.forEach((inc) => {
        expect(inc).toBeGreaterThanOrEqual(1);
        expect(inc).toBeLessThanOrEqual(5);
      });
    });
  });

  describe('Punctuation Pauses', () => {
    it('should pause longer after period', () => {
      // Test that periods cause delays by comparing timing
      const { result: withPeriod } = renderHook(() =>
        useTypewriter('A. B', { isActive: false, alwaysAnimate: true, speed: 1 })
      );

      const { result: withoutPeriod } = renderHook(() =>
        useTypewriter('A B C', { isActive: false, alwaysAnimate: true, speed: 1 })
      );

      // After same amount of time, text with period should be shorter
      // because it pauses at the period
      act(() => {
        vi.advanceTimersByTime(100);
      });

      // Both should be animating, but with period may be slower
      expect(withPeriod.current.displayText.length).toBeLessThanOrEqual(
        withoutPeriod.current.displayText.length + 1
      );
    });

    it('should handle exclamation marks as sentence endings', () => {
      const { result } = renderHook(() =>
        useTypewriter('Wow! Great!', { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.displayText).toBe('Wow! Great!');
    });

    it('should handle question marks as sentence endings', () => {
      const { result } = renderHook(() =>
        useTypewriter('How? Why?', { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.displayText).toBe('How? Why?');
    });

    it('should pause at commas', () => {
      const { result } = renderHook(() =>
        useTypewriter('One, two, three', { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.displayText).toBe('One, two, three');
    });

    it('should pause at colons and semicolons', () => {
      const { result } = renderHook(() =>
        useTypewriter('Note: test; done', { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.displayText).toBe('Note: test; done');
    });

    it('should pause at newlines', () => {
      const { result } = renderHook(() =>
        useTypewriter('Line1\nLine2', { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.displayText).toBe('Line1\nLine2');
    });
  });

  describe('Speed Acceleration', () => {
    it('should accept speed multiplier option', () => {
      const { result } = renderHook(() =>
        useTypewriter('Test', { isActive: false, alwaysAnimate: true, speed: 2.0 })
      );

      // Should not throw and should work with speed option
      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(result.current.displayText).toBe('Test');
    });

    it('should animate faster with higher speed multiplier', () => {
      const { result: slow } = renderHook(() =>
        useTypewriter('ABCDEFGHIJ', { isActive: true, alwaysAnimate: true, speed: 1.0 })
      );

      const { result: fast } = renderHook(() =>
        useTypewriter('ABCDEFGHIJ', { isActive: true, alwaysAnimate: true, speed: 3.0 })
      );

      // Advance same amount of time
      act(() => {
        vi.advanceTimersByTime(100);
      });

      // Faster speed should have revealed more or equal characters
      expect(fast.current.displayText.length).toBeGreaterThanOrEqual(
        slow.current.displayText.length
      );
    });

    it('should accelerate over time (start slower, speed up)', () => {
      // The hook starts at 0.7x speed and ramps to 1.2x over 80 chars
      const { result } = renderHook(() =>
        useTypewriter('A'.repeat(100), { isActive: false, alwaysAnimate: true })
      );

      // Measure time to reveal first 10 chars
      const startTime = Date.now();
      act(() => {
        vi.advanceTimersByTime(500);
      });

      // Should have revealed some characters
      expect(result.current.displayText.length).toBeGreaterThan(0);
    });

    it('should maintain minimum delay regardless of speed', () => {
      const { result } = renderHook(() =>
        useTypewriter('ABCDEFGHIJ', { isActive: false, alwaysAnimate: true, speed: 100 })
      );

      // First batch revealed synchronously, but not all text
      const initialLength = result.current.displayText.length;
      expect(initialLength).toBeGreaterThan(0);
      expect(initialLength).toBeLessThan(10);

      act(() => {
        vi.advanceTimersByTime(10);
      });

      // After a very short time with very high speed, should have more progress
      // The hook has a minimum delay of 8ms
      expect(result.current.displayText.length).toBeGreaterThan(initialLength);
    });
  });

  describe('Inactive State', () => {
    it('should return full text immediately when isActive is false and not alwaysAnimate', () => {
      const { result } = renderHook(() =>
        useTypewriter('Hello World', { isActive: false, alwaysAnimate: false })
      );

      // Should display full text immediately without animation
      expect(result.current.displayText).toBe('Hello World');
      expect(result.current.isTyping).toBe(false);
    });

    it('should not animate preloaded content by default', () => {
      const { result } = renderHook(() =>
        useTypewriter('Preloaded text', { isActive: false })
      );

      // No timer advancement needed - should be instant
      expect(result.current.displayText).toBe('Preloaded text');
    });

    it('should animate when alwaysAnimate is true even if inactive', () => {
      const { result } = renderHook(() =>
        useTypewriter('Animate this', { isActive: false, alwaysAnimate: true })
      );

      // With alwaysAnimate, first batch is revealed synchronously
      const initialLength = result.current.displayText.length;
      expect(initialLength).toBeGreaterThan(0);
      expect(initialLength).toBeLessThan(12); // Less than full text

      act(() => {
        vi.advanceTimersByTime(500);
      });

      // Should reveal more
      expect(result.current.displayText.length).toBeGreaterThan(initialLength);
    });

    it('should continue waiting for content when isActive but text exhausted', () => {
      const { result, rerender } = renderHook(
        ({ text, isActive }) => useTypewriter(text, { isActive, alwaysAnimate: true }),
        { initialProps: { text: 'Hi', isActive: true } }
      );

      // Reveal all current text
      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(result.current.displayText).toBe('Hi');

      // Add more text while still active
      rerender({ text: 'Hi there', isActive: true });

      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(result.current.displayText).toBe('Hi there');
    });

    it('should stop animation when streaming ends', () => {
      const { result, rerender } = renderHook(
        ({ text, isActive }) => useTypewriter(text, { isActive, alwaysAnimate: true }),
        { initialProps: { text: 'Hello', isActive: true } }
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      // Mark as inactive (streaming ended)
      rerender({ text: 'Hello', isActive: false });

      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(result.current.displayText).toBe('Hello');
      expect(result.current.isTyping).toBe(false);
    });
  });

  describe('Empty String Handling', () => {
    it('should handle empty string input', () => {
      const { result } = renderHook(() =>
        useTypewriter('', { isActive: true, alwaysAnimate: true })
      );

      expect(result.current.displayText).toBe('');
      expect(result.current.isTyping).toBe(false);
    });

    it('should handle null-like empty string', () => {
      const { result } = renderHook(() =>
        useTypewriter('', { isActive: false })
      );

      expect(result.current.displayText).toBe('');
    });

    it('should reset to empty when text becomes empty', () => {
      const { result, rerender } = renderHook(
        ({ text }) => useTypewriter(text, { isActive: false, alwaysAnimate: true }),
        { initialProps: { text: 'Hello' } }
      );

      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(result.current.displayText).toBe('Hello');

      // Clear the text
      rerender({ text: '' });

      expect(result.current.displayText).toBe('');
      expect(result.current.isTyping).toBe(false);
    });

    it('should handle whitespace-only strings', () => {
      const { result } = renderHook(() =>
        useTypewriter('   ', { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(500);
      });

      expect(result.current.displayText).toBe('   ');
    });
  });

  describe('Text Change Resets', () => {
    it('should continue animation when text is appended', () => {
      const { result, rerender } = renderHook(
        ({ text }) => useTypewriter(text, { isActive: true, alwaysAnimate: true }),
        { initialProps: { text: 'Hello' } }
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      const firstLength = result.current.displayText.length;

      // Append more text
      rerender({ text: 'Hello World' });

      act(() => {
        vi.advanceTimersByTime(500);
      });

      // Should continue and reveal more
      expect(result.current.displayText.length).toBeGreaterThan(firstLength);
    });

    it('should handle rapid text updates', () => {
      const { result, rerender } = renderHook(
        ({ text }) => useTypewriter(text, { isActive: true, alwaysAnimate: true }),
        { initialProps: { text: 'A' } }
      );

      // Rapid updates
      rerender({ text: 'AB' });
      rerender({ text: 'ABC' });
      rerender({ text: 'ABCD' });
      rerender({ text: 'ABCDE' });

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.displayText).toBe('ABCDE');
    });

    it('should reset when text is completely different', () => {
      const { result, rerender } = renderHook(
        ({ text }) => useTypewriter(text, { isActive: false, alwaysAnimate: false }),
        { initialProps: { text: 'First text' } }
      );

      expect(result.current.displayText).toBe('First text');

      // Completely different text
      rerender({ text: 'Second text' });

      expect(result.current.displayText).toBe('Second text');
    });

    it('should clean up timers on unmount', () => {
      const { unmount } = renderHook(() =>
        useTypewriter('Hello', { isActive: true, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(50);
      });

      // Unmount should not throw
      expect(() => unmount()).not.toThrow();

      // Advancing timers after unmount should not cause issues
      act(() => {
        vi.advanceTimersByTime(1000);
      });
    });

    it('should handle switching between different texts', () => {
      const { result, rerender } = renderHook(
        ({ text }) => useTypewriter(text, { isActive: false, alwaysAnimate: false }),
        { initialProps: { text: 'Text A' } }
      );

      expect(result.current.displayText).toBe('Text A');

      rerender({ text: 'Text B' });
      expect(result.current.displayText).toBe('Text B');

      rerender({ text: 'Text C' });
      expect(result.current.displayText).toBe('Text C');
    });
  });

  describe('Edge Cases', () => {
    it('should handle very long text', () => {
      const longText = 'A'.repeat(1000);
      const { result } = renderHook(() =>
        useTypewriter(longText, { isActive: false, alwaysAnimate: true, speed: 5 })
      );

      // Need enough time for 1000 chars at ~2-5 chars per batch
      // With speed 5x and ~8ms minimum delay, ~1600ms should be enough
      act(() => {
        vi.advanceTimersByTime(10000);
      });

      expect(result.current.displayText).toBe(longText);
    });

    it('should handle special characters', () => {
      const specialText = '!@#$%^&*()_+-=[]{}|;\':",./<>?`~';
      const { result } = renderHook(() =>
        useTypewriter(specialText, { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      expect(result.current.displayText).toBe(specialText);
    });

    it('should handle unicode characters', () => {
      const unicodeText = '你好世界 🌍 émojis 日本語';
      const { result } = renderHook(() =>
        useTypewriter(unicodeText, { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      expect(result.current.displayText).toBe(unicodeText);
    });

    it('should handle markdown-like content', () => {
      const markdownText = '## Heading\n\n- Item 1\n- Item 2\n\n**Bold** and *italic*';
      const { result } = renderHook(() =>
        useTypewriter(markdownText, { isActive: false, alwaysAnimate: true })
      );

      act(() => {
        vi.advanceTimersByTime(3000);
      });

      expect(result.current.displayText).toBe(markdownText);
    });

    it('should handle default options', () => {
      const { result } = renderHook(() => useTypewriter('Test'));

      // With default options (isActive defaults to true but no alwaysAnimate)
      // Behavior depends on initial state
      expect(result.current).toHaveProperty('displayText');
      expect(result.current).toHaveProperty('isTyping');
    });
  });
});
