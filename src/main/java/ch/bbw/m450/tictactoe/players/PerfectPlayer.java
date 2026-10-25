package ch.bbw.m450.tictactoe.players;

import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

import ch.bbw.m450.tictactoe.TicTacToeMain;
import ch.bbw.m450.tictactoe.TicTacToePlayer;

/** Chooses a move with the best possible outcome against an optimal opponent. */
public class PerfectPlayer implements TicTacToePlayer {

	@Override
	public int play(Stone[] board, Stone colorToPlay) {
		var positions = Arrays.copyOf(board, board.length);
		var scores = new HashMap<String, Integer>();
		var bestMove = -1;
		var bestScore = Integer.MIN_VALUE;
		for (var i = 0; i < positions.length; i++) {
			if (positions[i] == null) {
				positions[i] = colorToPlay;
				var score = evaluate(positions, colorToPlay.opponent(), colorToPlay, scores);
				positions[i] = null;
				if (score > bestScore) {
					bestScore = score;
					bestMove = i;
				}
			}
		}
		if (bestMove < 0) {
			throw new IllegalStateException("cannot play at all");
		}
		return bestMove;
	}

	private static int evaluate(Stone[] board, Stone turn, Stone ownColor, Map<String, Integer> scores) {
		if (TicTacToeMain.isWin(board, ownColor)) {
			return 1;
		}
		if (TicTacToeMain.isWin(board, ownColor.opponent())) {
			return -1;
		}
		var key = Arrays.toString(board) + turn;
		if (scores.containsKey(key)) {
			return scores.get(key);
		}
		var best = turn == ownColor ? Integer.MIN_VALUE : Integer.MAX_VALUE;
		for (var i = 0; i < board.length; i++) {
			if (board[i] == null) {
				board[i] = turn;
				var result = evaluate(board, turn.opponent(), ownColor, scores);
				board[i] = null;
				best = turn == ownColor ? Math.max(best, result) : Math.min(best, result);
			}
		}
		var score = best == Integer.MIN_VALUE || best == Integer.MAX_VALUE ? 0 : best;
		scores.put(key, score);
		return score;
	}
}
